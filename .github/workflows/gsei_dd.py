import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import time
from datetime import datetime
import hmac
import base64
import hashlib
import json
from urllib.parse import quote_plus
import os

class DingTalkMessenger:
    def __init__(self, token=None, secret=None):
        self.timestamp = str(round(time.time() * 1000))
        self.URL = 'https://oapi.dingtalk.com/robot/send'
        self.headers = {'Content-Type': 'application/json'}
        self.token = token or os.getenv('DD_ACCESS_TOKEN')
        self.secret = secret or os.getenv('DD_SECRET')
        self.sign = self.generate_sign()
        self.params = {'access_token': self.token, 'sign': self.sign}

    def generate_sign(self):
        secret_enc = self.secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(self.timestamp, self.secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        return quote_plus(base64.b64encode(hmac_code))

    def send_markdown(self, title, text):
        data = {
            'msgtype': 'markdown',
            'markdown': {
                'title': title,
                'text': text
            }
        }
        self.params['timestamp'] = self.timestamp
        try:
            response = requests.post(
                url=self.URL,
                data=json.dumps(data),
                params=self.params,
                headers=self.headers
            )
            response.raise_for_status()
            print("钉钉消息发送成功")
            return response
        except Exception as e:
            print(f"钉钉消息发送失败: {str(e)}")
            return None

class GSEISpider:
    def __init__(self, dingtalk_token=None, dingtalk_secret=None):
        self.base_url = "https://www.gsei.com.cn"
        self.start_url = "https://www.gsei.com.cn/html/1336/"  # 公开招标栏目URL
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.dingtalk = DingTalkMessenger(token=dingtalk_token, secret=dingtalk_secret) if (dingtalk_token and dingtalk_secret) else None
        # 用于存储已发送的招标信息
        self.sent_links_file = f"sent_links_{self.today}.json"
        self.sent_links = self.load_sent_links()

    def load_sent_links(self):
        """加载已发送的链接"""
        if os.path.exists(self.sent_links_file):
            try:
                with open(self.sent_links_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载已发送链接失败: {str(e)}")
        return []

    def save_sent_links(self, links):
        """保存已发送的链接"""
        try:
            with open(self.sent_links_file, 'w', encoding='utf-8') as f:
                json.dump(links, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存已发送链接失败: {str(e)}")

    def extract_date_from_url(self, url):
        """从URL中提取日期"""
        match = re.search(r'/(\d{4}-\d{2}-\d{2})/', url)
        if match:
            return match.group(1)
        return None

    def is_public_bidding(self, title, url):
        """判断是否为公开招标信息"""
        exclude_keywords = ['结果', '中标', '流标', '废标', '更正', '变更', '补充', '答疑', '澄清', '延期']
        if any(keyword in title for keyword in exclude_keywords):
            return False
        if '/html/1336/' not in url:
            return False
        return True

    def get_page_links(self, page_url):
        """获取指定页面的所有招标链接，并筛选出当天的公开招标链接"""
        try:
            response = self.session.get(page_url, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'content-' in href and href.endswith('.html'):
                    full_url = urljoin(self.base_url, href)
                    
                    url_date = self.extract_date_from_url(full_url)
                    if not url_date or url_date != self.today:
                        continue
                        
                    title = a.get_text(strip=True)
                    if not self.is_public_bidding(title, full_url):
                        continue
                        
                    if title and '下一页' not in title and '>>' not in title and '末页' not in title:
                        links.append({
                            '标题': title,
                            '链接': full_url,
                            '发布日期': url_date,
                            '添加时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        })
            return links
        except Exception as e:
            print(f"获取页面 {page_url} 时出错: {str(e)}")
            return []

    def format_dingtalk_message(self, results):
        """格式化钉钉消息"""
        if not results:
            return f"## {self.today} 无新招标信息\n\n今日没有找到新的公开招标信息。"
            
        message = f"## {self.today} 公开招标信息更新\n\n"
        
        # 获取当前已发送的链接
        sent_links = [item['链接'] for item in self.sent_links]
        
        # 只获取未发送过的新信息
        new_results = [item for item in results if item['链接'] not in sent_links]
        
        if not new_results:
            return f"## {self.today} 无新招标信息\n\n今日没有找到新的公开招标信息。"
        
        # 将新信息添加到已发送列表的前面（保持倒序）
        self.sent_links = new_results + self.sent_links
        self.save_sent_links(self.sent_links)
        
        # 为所有信息编号（从1开始）
        for i, item in enumerate(self.sent_links, 1):
            message += f"### {i}. {item['标题']}\n"
            message += f"- 原文链接：[点击查看]({item['链接']})\n"
            message += f"- 发布日期：{item['发布日期']}\n\n"
        
        return message

    def send_to_dingtalk(self, results):
        """发送消息到钉钉"""
        if not self.dingtalk:
            print("未配置钉钉机器人，跳过消息推送")
            return False
            
        message = self.format_dingtalk_message(results)
        title = f"{self.today} 公开招标信息更新"
        return self.dingtalk.send_markdown(title, message)

    def crawl(self, max_pages=10, send_dingtalk=True):
        """爬取当天的公开招标信息"""
        all_links = []
        current_page = 1
        found_today = False
        
        print(f"开始爬取 {self.today} 的公开招标信息...")
        
        while current_page <= max_pages:
            if current_page == 1:
                page_url = self.start_url
            else:
                page_url = f"https://www.gsei.com.cn/html/1336/list-{current_page}.html"
            
            print(f"正在爬取第 {current_page} 页: {page_url}")
            links = self.get_page_links(page_url)
            
            if links:
                all_links.extend(links)
                found_today = True
            elif found_today:
                print(f"已找到 {self.today} 的所有公开招标信息，停止爬取。")
                break
            elif current_page > 3:
                print(f"已经检查了 {current_page} 页，但没有找到 {self.today} 的公开招标信息。")
                break
                
            current_page += 1
            time.sleep(2)
        
        if all_links:
            print(f"\n爬取完成！共获取 {len(all_links)} 条 {self.today} 的公开招标信息")
            
            # 发送钉钉通知
            if send_dingtalk:
                self.send_to_dingtalk(all_links)
        else:
            print(f"未找到 {self.today} 的公开招标信息")
            if send_dingtalk:
                self.dingtalk.send_markdown(
                    f"{self.today} 无新招标信息",
                    f"## {self.today} 无新招标信息\n\n未找到今日的公开招标信息。"
                )

        return all_links

if __name__ == "__main__":
    # 替换为您的钉钉机器人token和secret
    DINGTALK_TOKEN = os.getenv('DD_ACCESS_TOKEN')
    DINGTALK_SECRET = os.getenv('DD_SECRET')
    
    # 创建爬虫实例并运行
    spider = GSEISpider(
        dingtalk_token=DINGTALK_TOKEN,
        dingtalk_secret=DINGTALK_SECRET
    )
    
    # 开始爬取，并发送钉钉通知
    spider.crawl(max_pages=10)
