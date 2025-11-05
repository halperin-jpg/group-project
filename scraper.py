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
    STOPWORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 
    'any', 'are', "aren't", 'as', 'at', 'be', 'because', 'been', 'before', 'being', 
    'below', 'between', 'both', 'but', 'by', "can't", 'cannot', 'could', "couldn't", 
    'did', "didn't", 'do', 'does', "doesn't", 'doing', "don't", 'down', 'during', 
    'each', 'few', 'for', 'from', 'further', 'had', "hadn't", 'has', "hasn't", 
    'have', "haven't", 'having', 'he', "he'd", "he'll", "he's", 'her', 'here', 
    "here's", 'hers', 'herself', 'him', 'himself', 'his', 'how', "how's", 'i', 
    "i'd", "i'll", "i'm", "i've", 'if', 'in', 'into', 'is', "isn't", 'it', "it's", 
    'its', 'itself', "let's", 'me', 'more', 'most', "mustn't", 'my', 'myself', 
    'no', 'nor', 'not', 'of', 'off', 'on', 'once', 'only', 'or', 'other', 'ought', 
    'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', "shan't", 'she', 
    "she'd", "she'll", "she's", 'should', "shouldn't", 'so', 'some', 'such', 
    'than', 'that', "that's", 'the', 'their', 'theirs', 'them', 'themselves', 
    'then', 'there', "there's", 'these', 'they', "they'd", "they'll", "they're", 
    "they've", 'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 
    'very', 'was', "wasn't", 'we', "we'd", "we'll", "we're", "we've", 'were', 
    "weren't", 'what', "what's", 'when', "when's", 'where', "where's", 'which', 
    'while', 'who', "who's", 'whom', 'why', "why's", 'with', "won't", 'would', 
    "wouldn't", 'you', "you'd", "you'll", "you're", "you've", 'your', 'yours', 
    'yourself', 'yourselves', 'cc', 'cl', 'nc', 'oc', 'nh', 'occ', 'ccc', 'us', 
    'one', 'may', 'can', 'will', 'also', 'much', 'well', 'back', 'even',
    'just', 'way', 'get', 'make', 'go', 'see', 'know', 'take', 'use', 'find', 
    's', 'd', 'p', 'b', 'm', 'j', 'n', 'e', 't', 'o', '10', '2017', '2018', 
    '2019', '2020', '2021', '2022', '2023', '2024', '2025'
}

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
                netloc = url_parsed.netloc.lower()
                if netloc.endswith('.uci.edu') or netloc == 'uci.edu':
                    with lock_domains:
                        domain_counts[netloc] += 1
        
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
    try:
        parsed_url = urlparse(url)
                if parsed_url.scheme not in {"http", "https"}:
            return False
        
        allowed_domains = ["ics.uci.edu", "cs.uci.edu", "informatics.uci.edu", "stat.uci.edu"]
        if not any(parsed_url.netloc.lower().endswith(domain) for domain in allowed_domains):
            return False
        
        banned_hosts = ["wics.ics.uci.edu", "ngs.ics.uci.edu", "www.cecs.uci.edu"]
        if parsed_url.netloc.lower() in banned_hosts:
            return False
        
        normalized_url = url.lower()
        path_part = (parsed_url.path or "").lower()
        query_part = (parsed_url.query or "").lower()
        
        if "wp-login" in normalized_url:
            return False
        
        if "grape.ics.uci.edu/wiki" in normalized_url:
            wiki_blocked = ["/asterix", "/public/zip-attachment", "/public/raw-attachment", 
                           "/public/wiki", "/public/timeline"]
            if any(blocked in path_part for blocked in wiki_blocked):
                return False
        
        if "/events" in path_part:
            if any(host in normalized_url for host in ["ics.uci.edu", "isg.ics.uci.edu"]):
                return False
        
        if "tribe" in query_part or "tribe" in path_part:
            return False
        
        if "mlphysics.ics.uci.edu" in normalized_url and "/data" in path_part:
            return False
        
        if "~babaks/bwr" in normalized_url and "home_files" in path_part:
            return False
        
        if re.search(r"^https?://www\.stat\.uci\.edu/wp-content/uploads/[A-Za-z\-]+-?Abstract-?\d{1,2}-\d{1,2}-(?:\d{2}|\d{4})", url):
            return False
        
        if re.search(r"^https?://www\.stat\.uci\.edu/ICS/statistics/research/seminarseries/\d{4}-\d{4}/index$", url):
            return False
        
        if re.search(r"[?&](?:ical|outlook-ical)=\d+", url):
            return False
        
        if re.search(r"^https?://helpdesk\.ics\.uci\.edu/Ticket/Display\.html\?id=\d+$", url):
            return False
        
        if "doku.php" in normalized_url:
            return False
        
        if re.search(r"^https?://(?:www\.)?ics\.uci\.edu/~eppstein/pix", url):
            return False
        
        if re.search(r"[?&]format=txt", normalized_url):
            return False
        
        if re.search(r"^https?://www\.ics\.uci\.edu/~ziv/.*\.htm$", url):
            return False
        
        if "wics.ics.uci.edu" in normalized_url and ("?share=twitter" in normalized_url or "?share=facebook" in normalized_url or "attachment" in normalized_url):
            return False
        
        # General bad patterns
        problematic_patterns = [
            r'/calendar', r'/login', r'/logout', r'/signup', r'/register', 
            r'/wp-json', r'/wp-admin', r'/~eppstein/pubs',
            r'filter', r'sort', r'share', r'replytocom', r'feed', r'session'
        ]
        
        for pattern in problematic_patterns:
            if re.search(pattern, normalized_url):
                return False
        
        if len(url) > 250:
            return False
        
        path_segments = [segment for segment in path_part.split('/') if segment]
        if len(path_segments) != len(set(path_segments)):
            return False
        
        if parsed_url.query:
            if len(parsed_url.query.split('&')) > 4:
                return False
            if re.search(r'(page|p|offset|limit)=\d+', query_part):
                return False
        
        if re.search(r'(replytocom|comments?|reply)', query_part):
            return False
        
        # Filter file extensions
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz"
            + r"|svg|xml|img|apk|bib|htm|odc|pps|ppsx|lif|rle|nb|tsv|Z|ma)$", path_part)
    
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
    
    uci_subdomains = {domain: count for domain, count in domain_counts.items() 
                      if domain.endswith('.uci.edu') or domain == 'uci.edu'}
    sorted_domains = sorted(uci_subdomains.items())
    output.append(f"4. Subdomains found in uci.edu domain: {len(sorted_domains)}")
    output.append("   Subdomain, Unique Pages:")
    for domain, count in sorted_domains:
        output.append(f"   {domain}, {count}")
    
    report_text = "\n".join(output)
    
    with open("report.txt", "w", encoding="utf-8") as f:
        f.write(report_text)
    
    print(report_text)