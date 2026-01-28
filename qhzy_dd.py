import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import time
import hmac
import base64
import hashlib
import json
from urllib.parse import quote_plus, urljoin
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
        string_to_sign = f"{self.timestamp}\n{self.secret}"
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
                data=json.dumps(data, ensure_ascii=False).encode('utf-8'),
                params=self.params,
                headers=self.headers
            )
            response.raise_for_status()
            print("钉钉消息发送成功")
            return response
        except Exception as e:
            print(f"钉钉消息发送失败: {str(e)}")
            return None

class QinHuangDaoSpider:
    def __init__(self, dingtalk_token=None, dingtalk_secret=None):
        self.base_url = "https://www.qhdzzbfw.gov.cn"
        self.start_url = "https://www.qhdzzbfw.gov.cn/ggzy/jyxx/001001/001001001/transinfo_list.html"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.today = datetime.now().strftime('%Y-%m-%d')
        self.dingtalk = DingTalkMessenger(token=dingtalk_token, secret=dingtalk_secret) if (dingtalk_token and dingtalk_secret) else None
        self.sent_links = []  # 用于存储已发送的链接

    def get_page_links(self, page_url):
        """获取指定页面的所有招标链接"""
        try:
            response = self.session.get(page_url, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            links = []
            # 找到所有招标信息行
            rows = soup.select('.ewb-trade-list li')
            
            for row in rows:
                try:
                    # 获取标题和链接
                    a_tag = row.select_one('a')
                    if not a_tag:
                        continue
                        
                    title = a_tag.get_text(strip=True)
                    relative_url = a_tag.get('href', '')
                    full_url = urljoin(self.base_url, relative_url)
                    
                    # 获取日期
                    date_span = row.select_one('.ewb-list-date')
                    if date_span:
                        date_str = date_span.get_text(strip=True)
                        # 尝试解析日期
                        try:
                            publish_date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
                        except:
                            publish_date = self.today
                    else:
                        publish_date = self.today
                    
                    # 只获取当天的信息
                    if publish_date != self.today:
                        continue
                        
                    links.append({
                        '标题': title,
                        '链接': full_url,
                        '发布日期': publish_date,
                        '添加时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                except Exception as e:
                    print(f"处理行时出错: {str(e)}")
                    continue
                    
            return links
            
        except Exception as e:
            print(f"获取页面 {page_url} 时出错: {str(e)}")
            return []

    def format_dingtalk_message(self, results):
        """格式化钉钉消息"""
        if not results:
            return f"## {self.today} 无新招标信息\n\n今日没有找到新的公开招标信息。"
            
        message = f"## {self.today} 青海省公共资源交易中心招标信息\n\n"
        
        # 获取当前已发送的链接
        sent_links = [item['链接'] for item in self.sent_links]
        
        # 只获取未发送过的新信息
        new_results = [item for item in results if item['链接'] not in sent_links]
        
        if not new_results:
            return f"## {self.today} 无新招标信息\n\n今日没有找到新的公开招标信息。"
        
        # 将新信息添加到已发送列表的前面（保持倒序）
        self.sent_links = new_results + self.sent_links
        
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
        title = f"{self.today} 青海省招标信息更新"
        return self.dingtalk.send_markdown(title, message)

    def crawl(self, max_pages=5, send_dingtalk=True):
        """爬取当天的公开招标信息"""
        all_links = []
        
        print(f"开始爬取 {self.today} 的青海省公开招标信息...")
        
        # 获取第一页
        print(f"正在爬取第 1 页: {self.start_url}")
        links = self.get_page_links(self.start_url)
        if links:
            all_links.extend(links)
            print(f"第 1 页找到 {len(links)} 条招标信息")
        else:
            print("第 1 页没有找到招标信息")
        
        # 如果启用了钉钉通知，则发送消息
        if all_links and send_dingtalk:
            self.send_to_dingtalk(all_links)
        elif not all_links:
            print(f"未找到 {self.today} 的公开招标信息")
            if send_dingtalk and self.dingtalk:
                self.dingtalk.send_markdown(
                    f"{self.today} 无新招标信息",
                    f"## {self.today} 无新招标信息\n\n未找到今日的公开招标信息。"
                )

        return all_links

if __name__ == "__main__":
    # 从环境变量中获取钉钉机器人token和secret
    DINGTALK_TOKEN = os.getenv('DD_ACCESS_TOKEN_xq')
    DINGTALK_SECRET = os.getenv('DD_SECRET_xq')
    
    if not DINGTALK_TOKEN or not DINGTALK_SECRET:
        print("错误：未设置钉钉机器人token或secret")
        print("请在环境变量中设置 DD_ACCESS_TOKEN 和 DD_SECRET")
        exit(1)
    
    # 创建爬虫实例并运行
    spider = QinHuangDaoSpider(
        dingtalk_token=DINGTALK_TOKEN,
        dingtalk_secret=DINGTALK_SECRET
    )
    
    # 开始爬取，并发送钉钉通知
    spider.crawl()
