# -*- coding: utf-8 -*-
import requests
from pyquery import PyQuery
import gevent
import logging
import functools
import redis
import datetime
from celery_app import app


import sys
sys.path.append('../')
from models import (
    Stock,
    Stock_Tag,
    base
)


redis_client = redis.Redis(host='localhost', port=6379,
                           db=1, decode_responses=True)

DMM_URL = 'http://www.dmm.co.jp/digital/anime/-/list/=/sort=ranking/'
logger = logging.getLogger("test")
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) ' \
             'AppleWebKit/537.36 (KHTML, like Gecko)'\
             ' Chrome/61.0.3163.100 Safari/537.36'

REQUEST_CACHE_TIMEOUT = 30 * 60 * 60 * 24  # 30 days
proxies = {"http": "socks5://127.0.0.1:10010"}


def pq(content):
    if content:
        return PyQuery(content)


def retry(times=3):
    def deco(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(times):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.exception("retry {} times exception.".format(i), e)
                    gevent.sleep(3)
                else:
                    break

        return wrapper

    return deco


def get_web_page(url, timeout=15):
    content = redis_client.get(url)
    if content:
        return content
    with requests.Session() as session:
        session.headers['User-Agent'] = USER_AGENT
        try:
            resp = session.get(url, timeout=timeout, proxies=proxies)
            if resp.status_code == 200:
                logger.warning('missing cache for url: {}'.format(url))
                content = resp.content
                redis_client.setex(url, content, REQUEST_CACHE_TIMEOUT)
                web_page = content.decode('utf8')
                return web_page
        except requests.exceptions.ConnectionError:
            # NOTE: do not raise and not retry
            pass
        logger.warning('Get web page {} error'.format(url))


@app.task
def worker(url):
    print(url)
    # print(get_web_page('http://pv.sohu.com/cityjson?ie=utf-8'))
    html = pq(get_web_page(url))
    works_name = html(".hreview h1").text()
    release_time = html(".mg-b20 tr").eq(2)("td").eq(1).text().split('/')
    length_time = html(".mg-b20 tr").eq(3)("td").eq(1).text()
    works_series = html(".mg-b20 tr").eq(4)("td").eq(1).text()
    company = html(".mg-b20 tr").eq(5)("td").eq(1).text()
    factory = html(".mg-b20 tr").eq(6)("td").eq(1).text()
    category = html(".mg-b20 tr").eq(7)("td").eq(1).text().split()
    cover = html("#sample-video > a")
    if cover:
        try:
            cover = "https://{}".format(cover.attr("href").split('://')[1])
        except IndexError:
            print(url)
            print(cover)
            cover = 'https://malu-picture.oss-cn-beijing.aliyuncs.com/18-5-11/3774354.jpg'

    else:
        cover = html("#sample-video  > img")
        cover = "https://{}".format(cover.attr("src").split('://')[1])
    Introduction = html(".lh4").text()
    Screenshots = ["https://{}".format(i.attr("src").split("://")[1])
                   for i in html("#sample-image-block img").items()]
    try:
        year = int(release_time[0])
        month = int(release_time[1])
        day = int(release_time[2])
    except ValueError:
        day = int(release_time[2].split(' ')[0])
    # print("作品名：{},\n发布时间:{}，\n影片时长:{}，\n影片系列：{}，\n公司：{}，\n厂商：{}，\n类别：{}, \ncover:{}, \n简介:{}, \n截图:{}".format(
    #     works_name,
    #     release_time,
    #     length_time,
    #     works_series,
    #     company,
    #     factory,
    #     category,
    #     cover,
    #     Introduction,
    #     Screenshots
    # ))
    session = base.DBSession()
    
    if session.query(Stock).filter(Stock.name == works_name).first():
        print("已经存在")
    else:
        tag = []
        for i in category:
            if session.query(Stock_Tag).filter(
                    Stock_Tag.tag == i).one_or_none() is None:
                sub = Stock_Tag(tag=i)
                session.add(sub)
                session.commit()
            tag.append(session.query(Stock_Tag).filter(
                Stock_Tag.tag == i).first().id)
    
        try:
            year = int(release_time[0])
            month = int(release_time[1])
            day = int(release_time[2])
        except ValueError:
            print(release_time)
            year = 1980
            month = 1
            day = 1
        sub = Stock(name=works_name,
                    introduction=Introduction,
                    cover=cover,
                    release_time=datetime.datetime(year, month, day),
                    length_time=length_time,
                    works_series=works_series,
                    company=company,
                    factory=factory,
                    category=",".join(str(i) for i in tag),
                    screenshots=",".join(i for i in Screenshots)
                    )
        session.add(sub)
        session.commit()
        print("插入成功")


def get_anime_link():
    anime_link = []
    # session = models.DBSession()
    for i in range(1, 18):
        html = pq(get_web_page("{}page={}/".format(DMM_URL, i)))
        for i in html("#list li .tmb a").items():
            # print(i.attr("href").split()[0])
            worker(i.attr("href"))


if __name__ == '__main__':
    worker('http://www.dmm.co.jp/digital/anime/-/detail/=/cid=62gbr00009/?i3_ref=list&i3_ord=7')
    # get_anime_link()