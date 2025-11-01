from threading import Thread, Lock
from urllib.parse import urlparse

from inspect import getsource
from utils.download import download
from utils import get_logger
import scraper
import time


class Worker(Thread):
    domain_locks = {}
    domain_last_access = {}
    domain_lock = Lock()

    def __init__(self, worker_id, config, frontier):
        self.worker_id = worker_id
        self.logger = get_logger(f"Worker-{worker_id}", "Worker")
        self.config = config
        self.frontier = frontier
        assert {getsource(scraper).find(req) for req in {"from requests import", "import requests"}} == {-1}, "Do not use requests in scraper.py"
        assert {getsource(scraper).find(req) for req in {"from urllib.request import", "import urllib.request"}} == {-1}, "Do not use urllib.request in scraper.py"
        super().__init__(daemon=True)
    
    def get_domain(self, url):
        parsed = urlparse(url)
        return parsed.netloc.lower()
    
    def wait_for_domain_politeness(self, domain):
        with Worker.domain_lock:
            if domain not in Worker.domain_locks:
                Worker.domain_locks[domain] = Lock()
                Worker.domain_last_access[domain] = 0
        
        domain_lock = Worker.domain_locks[domain]
        with domain_lock:
            current_time = time.time()
            last_access = Worker.domain_last_access.get(domain, 0)
            time_since_last = current_time - last_access
            
            if time_since_last < 0.5:
                sleep_time = 0.5 - time_since_last
                time.sleep(sleep_time)
            
            Worker.domain_last_access[domain] = time.time()
        
    def run(self):
        while True:
            tbd_url = self.frontier.get_tbd_url()
            if not tbd_url:
                self.logger.info("Frontier is empty. Stopping Crawler.")
                break
            
            domain = self.get_domain(tbd_url)
            print(f"Thread-{self.worker_id} handling: {tbd_url}")
            
            self.wait_for_domain_politeness(domain)
            
            resp = download(tbd_url, self.config, self.logger)
            self.logger.info(
                f"Downloaded {tbd_url}, status <{resp.status}>, "
                f"using cache {self.config.cache_server}.")
            scraped_urls = scraper.scraper(tbd_url, resp)
            for scraped_url in scraped_urls:
                self.frontier.add_url(scraped_url)
            self.frontier.mark_url_complete(tbd_url)
