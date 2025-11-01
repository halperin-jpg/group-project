import re
import os
import hashlib
from urllib.parse import urlparse, urljoin, urldefrag, urlunparse
from bs4 import BeautifulSoup
from collections import Counter, defaultdict
from threading import Lock

try:
    import nltk
    from nltk.corpus import stopwords
    try:
        STOPWORDS = set(stopwords.words('english'))
    except LookupError:
        nltk.download('stopwords', quiet=True)
        STOPWORDS = set(stopwords.words('english'))
except:
    STOPWORDS = {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'will', 'with'}

url_set = set()
domain_counts = defaultdict(int)
word_counts = Counter()
best_page = {'url': None, 'count': 0}
content_hashes = set()

lock_urls = Lock()
lock_domains = Lock()
lock_words = Lock()
lock_page = Lock()
lock_content = Lock()

def scraper(url, resp):
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]

def extract_next_links(url, resp):
    if resp is None or resp.status != 200 or resp.raw_response is None:
        return []
    
    if not resp.raw_response.headers.get('Content-Type', '').lower().startswith('text/html'):
        return []
    
    try:
        soup = BeautifulSoup(resp.raw_response.content, 'html.parser')
        
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        
        page_text = soup.get_text(separator=' ', strip=True)
        
        if len(page_text.strip()) < 50:
            return []
        
        content_hash = hashlib.md5(page_text.encode('utf-8')).hexdigest()
        with lock_content:
            if content_hash in content_hashes:
                return []
            content_hashes.add(content_hash)
        
        word_list = []
        current_word = []
        for char in page_text.lower():
            if char.isalnum():
                current_word.append(char)
            else:
                if current_word:
                    word_list.append(''.join(current_word))
                    current_word = []
        if current_word:
            word_list.append(''.join(current_word))
        
        if len(word_list) > 0:
            unique_set = set(word_list)
            if len(unique_set) / len(word_list) < 0.1:
                return []
        
        good_words = [w for w in word_list if w not in STOPWORDS and len(w) >= 3 and w.isalpha()]
        num_words = len(good_words)
        
        with lock_words:
            word_counts.update(good_words)
        
        with lock_page:
            if num_words > best_page['count']:
                best_page['count'] = num_words
                best_page['url'] = resp.url
        
        url_parsed = urlparse(resp.url)._replace(fragment="")
        clean_url = urlunparse(url_parsed)
        
        with lock_urls:
            if clean_url not in url_set:
                url_set.add(clean_url)
                parts = url_parsed.netloc.split('.')
                if len(parts) >= 2:
                    domain_base = '.'.join(parts[-2:])
                    if len(parts) > 2:
                        full_domain = '.'.join(parts[:-2]) + '.' + domain_base
                    else:
                        full_domain = domain_base
                    with lock_domains:
                        domain_counts[full_domain] += 1
        
    except Exception:
        pass
    
    try:
        soup_links = BeautifulSoup(resp.raw_response.content, 'html.parser')
        link_text = soup_links.get_text(separator=' ', strip=True)
        if len(link_text.strip()) < 50:
            return []
        
        found_links = set()
        base = resp.url or url
        for anchor in soup_links.find_all('a', href=True):
            link_href = anchor['href']
            if link_href.startswith(('mailto:', 'javascript:', '#', 'tel:')):
                continue
            try:
                full_link = urljoin(base, link_href)
                full_link, _ = urldefrag(full_link)
                full_link = full_link.strip()
                if full_link and full_link.endswith('/'):
                    full_link = full_link[:-1]
                if full_link:
                    found_links.add(full_link)
            except:
                continue
        
        return list(found_links)
        
    except Exception:
        return []

def is_valid(url):
    bad_urls = {
        "https://isg.ics.uci.edu/wp-login.php",
        "https://grape.ics.uci.edu/wiki/asterix",
        "https://ics.uci.edu/events/category/student-experience/day",
        "https://grape.ics.uci.edu/wiki/public/zip-attachment",
        "https://grape.ics.uci.edu/wiki/public/raw-attachment",
        "https://isg.ics.uci.edu/events",
        "https://grape.ics.uci.edu/wiki/public/wiki",
        "https://grape.ics.uci.edu/wiki/public/timeline?",
        "http://www.ics.uci.edu/~babaks/BWR/Home_files",
    }
    
    for bad in bad_urls:
        if url.startswith(bad):
            return False
    
    try:
        url_parts = urlparse(url)
        if url_parts.scheme not in {"http", "https"}:
            return False
        
        valid_domains = ["ics.uci.edu", "cs.uci.edu", "informatics.uci.edu", "stat.uci.edu"]
        
        if not any(url_parts.netloc.lower().endswith(d) for d in valid_domains):
            return False
        
        blocked = ["wics.ics.uci.edu", "ngs.ics.uci.edu", "www.cecs.uci.edu"]
        if url_parts.netloc.lower() in blocked:
            return False
        
        url_low = url.lower()
        path_low = (url_parts.path or "").lower()
        query_low = (url_parts.query or "").lower()
        
        if re.search(r"^https?://www\.stat\.uci\.edu/wp-content/uploads/[A-Za-z\-]+-?Abstract-?\d{1,2}-\d{1,2}-(?:\d{2}|\d{4})", url):
            return False
        
        if re.search(r"^https?://www\.stat\.uci\.edu/ICS/statistics/research/seminarseries/\d{4}-\d{4}/index$", url):
            return False
        
        if re.search(r"[?&](?:ical|outlook-ical)=\d+", url):
            return False
        
        if re.search(r"^https?://helpdesk\.ics\.uci\.edu/Ticket/Display\.html\?id=\d+$", url):
            return False
        
        if "doku.php" in url_low:
            return False
        
        if "?tribe" in url_low:
            return False
        
        if re.search(r"^https?://(?:www\.)?ics\.uci\.edu/~eppstein/pix", url):
            return False
        
        if re.search(r"[?&]format=txt", url_low):
            return False
        
        if "wp-login" in url_low:
            return False
        
        if re.search(r"^https?://www\.ics\.uci\.edu/~ziv/.*\.htm$", url):
            return False
        
        if "wics.ics.uci.edu" in url_low and ("?share=twitter" in url_low or "?share=facebook" in url_low or "/events" in url_low or "attachment" in url_low):
            return False
        
        if "ics.uci.edu/events/" in url_low:
            return False
        
        bad_patterns = [
            r'/calendar', r'/event', r'/events', r'/login', r'/logout',
            r'/signup', r'/register', r'/wp-json', r'/wp-admin',
            r'/doku\.php', r'/~eppstein/pix', r'/~eppstein/pubs',
            r'ical', r'tribe', r'filter', r'sort', r'share',
            r'replytocom', r'feed', r'session', r'/ca/rules/'
        ]
        
        for pattern in bad_patterns:
            if re.search(pattern, url_low):
                return False
        
        if len(url) > 250:
            return False
        
        path_segments = [s for s in path_low.split('/') if s]
        if len(path_segments) != len(set(path_segments)):
            return False
        
        if url_parts.query:
            if len(url_parts.query.split('&')) > 4:
                return False
            if re.search(r'(page|p|offset|limit)=\d+', query_low):
                return False
        
        if re.search(r'(replytocom|comments?|reply|feed)', query_low):
            return False
        
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz"
            + r"|svg|xml|img|apk|bib|htm|odc|pps|ppsx|lif|rle|nb|tsv|Z|ma)$", path_low)
    
    except (TypeError, AttributeError, ValueError):
        return False

def generate_report():
    if not os.path.exists("Logs"):
        os.makedirs("Logs")
    
    output = []
    
    output.append(f"1. Unique pages found: {len(url_set)}\n")
    
    if best_page['url']:
        output.append(f"2. Longest page: {best_page['url']}")
        output.append(f"   Word count: {best_page['count']}\n")
    else:
        output.append("2. Longest page: No pages crawled\n")
    
    top_words = word_counts.most_common(50)
    output.append("3. 50 most common words (excluding stop words):")
    for i, (word, freq) in enumerate(top_words, 1):
        output.append(f"   {i}. {word}: {freq}")
    output.append("")
    
    sorted_domains = sorted(domain_counts.items())
    output.append(f"4. Subdomains found: {len(sorted_domains)}")
    output.append("   Subdomain, Unique Pages:")
    for domain, count in sorted_domains:
        output.append(f"   {domain}, {count}")
    
    report_text = "\n".join(output)
    
    with open("report.txt", "w", encoding="utf-8") as f:
        f.write(report_text)
    
    print(report_text)
