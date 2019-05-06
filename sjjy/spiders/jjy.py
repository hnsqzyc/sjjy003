# -*- coding: utf-8 -*-
import scrapy
import json
import re
import os
import csv
import codecs
import copy
import hashlib
import time
import logging
from random import choice
from sjjy.user_ids import user_id
from scrapy import signals
from scrapy.item import Item, Field
from scrapy.http import Request, FormRequest
from scrapy.utils.project import get_project_settings
from sjjy.connection import RedisConnection, MongodbConnection

settings = get_project_settings()


class UniversalRow(Item):
    # This is a row wrapper. The key is row and the value is a dict
    # The dict wraps key-values of all fields and their values
    row = Field()
    table = Field()
    image_urls = Field()


class JjySpider(scrapy.Spider):
    name = 'jjy'

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(JjySpider, cls).from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_opened, signals.spider_opened)
        crawler.signals.connect(spider.spider_closed, signals.spider_closed)

        return spider

    def __init__(self, params, *args, **kwargs):

        super(JjySpider, self).__init__(self.name, *args, **kwargs)
        # dispatcher.connect(self.spider_closed, signals.spider_closed)
        paramsjson = json.loads(params)
        self.remote_resource = paramsjson.get('remote_resource', True)
        self.enable_proxy = paramsjson.get('enable_proxy', True)

    def spider_opened(self, spider):
        logging.info("爬取开始了...")

        self.redis_conn = RedisConnection(settings['REDIS']).get_conn()
        self.mongo_conn = MongodbConnection(settings['MONGODB']).get_conn()
        self.db = self.mongo_conn.sjjy
        self.sjjy = self.db.sjjy

    def spider_closed(self, spider):

        logging.info('爬取结束了..')

    def start_requests(self):
        while 1:
            # res = self.sjjy.find({'photo_num': {'$gt': 4, '$ne': 900}, 'status': 1}, {'_id': 0, 'realUid': 1, 'sexValue': 1, 'img_url_li': 1}).limit(100)
            res = self.sjjy.find({'status':7, 'photo_num':{'$gte':5, '$ne': 900},'img_url_li':{'$ne':[]}}, {'_id': 0, 'realUid': 1, 'sexValue': 1, 'img_url_li': 1}).limit(100)
            # print(res)
            if res.count():
                for info in res:
                    realUid = info.get('realUid')
                    sexValue = info.get('sexValue')

                    if info['img_url_li'][0][0].endswith('zchykj_f_bp.jpg') or info['img_url_li'][0][0].endswith('yzphykj_f_bp.jpg'):
                        logging.warning('注册和有图片权限限制, 待使用登陆用户访问...修改状态码为8...')
                        result = self.sjjy.update({'realUid': realUid}, {'$set': {'status': 8}})

                    elif info['img_url_li'][0][0].endswith('bp.jpg'):
                        logging.warning('星级或其它权限限制...修改状态码为9...')
                        result = self.sjjy.update({'realUid': realUid}, {'$set': {'status': 9}})

                    else:
                        for img_url in info['img_url_li'][0]:
                            # print(img_url)
                            meta = {}
                            meta['realUid'] = realUid
                            img_id = re.search(r'(.*?).jpg', img_url).group(1)[-7:]
                            head = re.search(r'http://(.*?)/', img_url).group(1)
                            header = {
                                "Host": head,
                                "Connection": "keep-alive",
                                "Upgrade-Insecure-Requests": "1",
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/72.0.3626.121 Safari/537.36",
                                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
                                "Referer": "http://www.jiayuan.com/{}?fxly=search_v2_index".format(realUid),
                                "Accept-Encoding": "gzip, deflate",
                                "Accept-Language": "zh-CN,zh;q=0.9"
                            }

                            if not os.path.exists(settings['DATA_DIR'] + str(realUid) + sexValue):
                                os.mkdir(settings['DATA_DIR'] + str(realUid) + sexValue)
                            save_location = os.path.join(settings['DATA_DIR'], str(realUid) + sexValue)

                            file_name = os.path.join(save_location, str(img_id) + '.jpg')

                            meta['file_name'] = file_name
                            logging.info(meta['file_name'])
                            logging.info('正在下载:' + file_name)
                            yield Request(url=img_url, headers=header, callback=self.download_image, meta=meta, priority=10)

                        logging.info('下载图片完成后修改Uid状态为2...')
                        print('realUid', realUid)
                        if self.sjjy.find({'realUid': realUid}, {'_id': 0, 'status': 1})[0].get('status') == 100:
                            # 重命名
                            logging.warning('重命名, 存在错误链接, 文件夹后缀 .bak')
                            # shutil.rmtree(save_location)
                            self.rename_file(save_location)
                            print('重命名成功... ')
                        else:
                            result = self.sjjy.update({'realUid': realUid}, {'$set': {'status': 2}})
            else:
                logging.warning('用户id采集完毕, return...')
                return

    def download_image(self, response):
        meta = response.request.meta
        res = response.body
        try:
            with open(meta['file_name'], 'wb') as f:
                f.write(res)
                f.close()
            logging.info('已经下载...')
        except FileNotFoundError:
            logging.warning('捕捉到文件名有误...')

    def rename_file(self, file_name):
        if os.path.exists(file_name):
            try:
                target_file = file_name + '.bak'
                os.rename(file_name, target_file)
            except:
                pass
