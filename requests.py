import urllib3
import certifi
import abc
import sys
import re
from hashlib import md5
from lxml import html
from collections import Counter
from dataclasses import dataclass
from random import choices
from time import sleep
from urllib.parse import parse_qs, quote, unquote, urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed

def first(x, default=[]):
    if x:
        return x[0]
    return default

def html_from_future(f):
    res = f.result()
    h = html.fromstring(res.data)
    h.url = res.geturl()
    return h


class BaseRequest(metaclass=abc.ABCMeta):

    def __init__(self, request_url, hop=0):
        self.request_url = request_url
        self.hop = hop
        self.graph_type = None

    @abc.abstractmethod
    def parse(self, res):
        pass

    @abc.abstractproperty
    def urls(self):
        pass

    @property
    def _name(self):
        return self.__class__.__name__


class AuthorSearch(BaseRequest):

    BASE_URL = ('https://scholar.google.com/citations?'
                + 'view_op=search_authors&mauthors=')

    def __init__(self, 
                 request_url,
                 max_page=10,
                 max_author_page=3):
        super().__init__(request_url)
        self.max_page = max_page
        self.max_author_page = max_author_page
        self.page = 1
    
    def parse(self, h):
        """
        Parses the html of a scholar search for an author at
        https://scholar.google.com/citations?view_op=search_authors

        h: [lxml.html] html object
        return: [(next)AuthorSeach, Authors...]
        """
        base = 'https://scholar.google.com'
        author_links = h.xpath('//div[@class="gs_ai_t"]/h3/a')
        authors = [
            Author(
                name=a.text,
                profile_name=a.text,
                author_id=parse_qs(a.get('href')).get('user')[0],
                max_page=self.max_author_page,
                request_url=base + a.get('href') + '&view_op=list_works'
            )
            for a in author_links
        ]
        # paginate by finding the "next page" button
        next_btn = h.xpath('//button[contains(@class, "gs_btnPR") and @onclick]')
        next_url = ''
        if next_btn:
            next_url = (base
                        + next_btn[0].get('onclick', '')
                                     .split('=')[-1]
                                     .strip("'")
                                     .replace('\\x', '%')
            )

        if next_url and (self.page < self.max_page):
            # create a new AuthorSearch for the next page
            next_page = self.__class__(next_url, max_page=self.max_page)
            next_page.page = self.page + 1
            next_search = [next_page]
        else:
            next_search = []
        return next_search + authors


    @property
    def urls(self):
        return [self.request_url]

    @classmethod
    def from_author_string(cls, author_str):
        aterm = quote(author_str, safe=' "').replace(' ', '+')
        url = cls.BASE_URL + aterm
        return cls(url)


class Author(BaseRequest):

    BASE_URL = 'https://scholar.google.com/citations?'

    def __init__(self, 
                 name='', 
                 profile_name='', 
                 author_id='', 
                 max_page=2,
                 request_url='', 
                 hop=0):
        super().__init__(request_url, hop)
        self.name = name
        self.profile_name = profile_name
        self.author_id = author_id
        self.max_page = max_page
        self.full_title = ''
        self.institution = ''
        self.email_domain = ''
        self.interests = []
        self.__set_key()

    def __eq__(self, other):
        if hasattr(other, '__hash__'):
            return self.__hash__()==other.__hash__()
        return False

    def __set_key(self):
        if self.author_id:
            self.__key = int(md5(self.author_id.encode('latin1')).hexdigest()[:16], 16)
        else:
            self.__key = int(md5(self.name.encode('latin1', errors='ignore')).hexdigest()[:16], 16)

    def __hash__(self):
        return self.__key

    def randomize_empty_id(self):
        """
        Set the empty `author_id` attribute to a random string.  Used for 
        authors without an author_id
        """
        s = '0123456789abcdefghijklmnopqrstuvwxyz'
        s += s.upper()
        if not self.author_id:
            self.author_id = '#' + ''.join(choices(s, k=8))
            self.__set_key
        return self.author_id

    def parse(self, h):
        """
        Parses an author's page. 

        h: [lxml.html] html object
        return: dict of the author id, profile name, and institution
        """
        # a blank generic type with a single method to handle missing elements
        blank = type('Element', (), {'text_content': lambda self: ''})
        
        # get all of the author information
        author_id = parse_qs(h.url.split('?')[-1]).get('user', [])[0]
        profile_name = first(h.xpath('//div[@id="gsc_prf_in"]')).text_content()
        full_title = first(h.xpath('//div[@class="gsc_prf_il"]'), blank()).text_content()
        institution = first(h.xpath('//a[@class="gsc_prf_ila"]'), blank()).text_content()
        email_domain = first(h.xpath('//div[@id="gsc_prf_ivh"]'), blank()).text_content()
        interests = h.xpath('//div[@id="gsc_prf_int"]/a/text()')

        # pull the title fragments for each publication.
        # title_fragments = [
        #     #a.text_content().split('  ')
        #     a.xpath('./text()')
        #     for a in h.xpath('//td[@class="gsc_a_t"]/a')
        # ]

        title_fragments = [
            [t.strip(' -\xa0\u2026') for t in a.xpath('./text()')]
            for a in h.xpath('//td[@class="gsc_a_t"]/a')
        ]

        title_fragments = [
            [
                f.strip() for frag in t_frags 
                for f in re.split(r'[^A-Za-z0-9;:" \[\]{},\.\-]+', frag) 
                if len(f.strip()) > 2
            ]
            for t_frags in title_fragments
        ]

        self.profile_name = profile_name
        self.author_id = author_id
        self.full_title = full_title
        self.institution = institution
        self.email_domain = email_domain
        self.interests = interests

        if self.max_page:
            # Authors always emit with a +1 hop
            queries = [
                TitleSearch.from_search_terms(t, self.hop+1, self) 
                for t in title_fragments
            ]
            return queries
        return []

    @property
    def urls(self):
        if not self.request_url:
            return []

        query_terms = {
            'user': self.author_id,
            'hl': 'en',
            'cstart': 0,
            'pagesize': 100,
            'view_op': 'list_works',
            'sortby': 'pubdate'
        }
        
        query_terms = {q: v for q, v in query_terms.items() if v is not None}

        if not self.max_page:
            return [self.BASE_URL + urlencode(query_terms)]
          
        url_list = []
        for i in range(self.max_page):
            query_terms['cstart'] = i * 100
            s_url = self.BASE_URL + urlencode(query_terms)
            url_list.append(s_url)
        return url_list


class TitleSearch(BaseRequest):

    BASE_URL = ('https://scholar.google.com/scholar'
                + '?as_vis=1&as_sdt=1,5&as_q=&as_occt=title&as_epq=')

    def __init__(self, request_url, hop=0, max_author_page=3, parent_author=None):
        self.parent_author = parent_author
        self.max_author_page = max_author_page
        super().__init__(request_url, hop)

    def parse(self, h):
        """
        Parses html search results when searching for a specific paper title.
        Useful when crawling from an author's page.

        h: [lxml.html] html object
        return: dictionary of document id, title, and authors of the first 
            search result.
        """
        return next(self._search_parser_gen(h))

    @property
    def urls(self):
        return [self.request_url]

    @classmethod
    def from_search_terms(cls, terms, hop=0, parent_author=None):
        terms = [
            quote(t, safe=' ()[]<>{}!^*~|').replace(' ', '+')
            for t in terms
        ]
        terms = [f'"{t}"' for t in terms]
        search_string = '+'.join(terms)
        url = cls.BASE_URL + search_string
        return cls(request_url=url, hop=hop, parent_author=parent_author)

    def _search_parser_gen(self, h):
        """
        Parses the html result of a scholar search for a general term.

        h: [lxml.html] html object
        return: geneartor that yields dictionaries of document id, title, 
            and authors.
        """
        
        doc_divs = h.xpath('//div[@data-did]')

        for div in doc_divs:
            doc_id = div.get('data-did')
            full_title = ''.join(div.xpath('.//h3/a/text()|.//h3/a/svg/@aria-label'))
            
            # \u2026 is ellipsis dots
            authors_nolink = [
                n
                for a in div.xpath('.//div[@class="gs_a"]/text()') 
                for n in a.split('\xa0')[0].strip('\u2026').split(', ')
            ]

            # max_page = 0 to stop the crawl at 1 hop
            authors_nolink = [
                Author(name=a, max_page=0)
                for a in authors_nolink if len(a) > 2
            ]
            
            authors_linked = [
                Author(
                    name=a.xpath('./text()')[0],
                    author_id=parse_qs(a.xpath('./@href')[0]).get('/citations?user', [''])[0],
                    max_page=self.max_author_page
                )
                for a in div.xpath('.//div[@class="gs_a"]/a')
            ]

            # pop the 'new' instance of the parent author
            if self.parent_author in authors_linked:
                authors_linked.pop(authors_linked.index(self.parent_author))
            # add in the original one
            authors_linked.append(self.parent_author)

            authors = authors_linked + authors_nolink

            yield Document(doc_id, full_title, self.parent_author, authors)


@dataclass
class Document:
    doc_id: str
    title: str
    parent_author: Author
    authors: list

    def __post_init__(self):
        self.__key = int(md5(self.doc_id.encode('latin1')).hexdigest()[:16], 16)

    @property
    def _name(self):
        return self.__class__.__name__

    def __hash__(self):
        return self.__key

    def __eq__(self, other):
        if hasattr(other, '__hash__'):
            return self.__hash__()==other.__hash__()
        return False


class RequestQueue:
    """
    Class for queuing up http requests to be processed.
    """

    def __init__(self, pool_size=5, delay=0.15):
        self._pool_size = pool_size
        self.thread_pool = ThreadPoolExecutor(pool_size)
        self.http_pool = urllib3.PoolManager(
            maxsize=self.pool_size,
            cert_reqs='CERT_REQUIRED',
            ca_certs=certifi.where()
        )
        self.headers = {
            'Host': 'scholar.google.com',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:70.0) Gecko/20100101 Firefox/70.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        self.futures = {}
        self.delay = delay

    def __repr__(self):
        r = (
            f'<RequestQueue {self.status.get("FREE")}/{self.pool_size} '
            f'threads free at 0x{id(self):x}>'
        )
        return r

    @property
    def pool_size(self):
        return self._pool_size

    def _add_url_request(self, 
                        url, 
                        pipeline=None,
                        callback=None, 
                        **kwargs):
        """
        Add a URL to the queue of requests.  For testing only.

        :param url: str, url to retrieve via http get request
        :param pipeline: callable, takes http response as positional arg
        :return f: future object

        Passing `pipeline` sends the result of the requested URL through
        `pipeline` before the thread closes.  This is primarily used to
        make parse a return for a new URL, then send an additional get request
        within the same thread.  It should be a callable that accepts one 
        positional argument, the urllib3.response.HTTPResponse of the request.
        The additional argument of `http_pool` is also passed to the object.
        """
        def target_fn(url, pipeline):
            if pipeline:
                return pipeline(self.http_pool.request('GET', url))
            return self.http_pool.request('GET', url)

        f = self.thread_pool.submit(target_fn, url, pipeline)
        self.futures[f] = url
        return f

    def add_request(self, req):
        """
        Add a Request object to the queue.
        """
        pr = self.http_pool.request

        def delayed(req, *args, **kwargs):
            sleep(self.delay)
            return req(*args, **kwargs)

        for url in req.urls:
            f = self.thread_pool.submit(delayed, pr, 'GET', url, headers=self.headers)
            #f.add_done_callback(req.callback)
            self.futures[f] = req
            #yield f

    def retrieve_completed(self):
        completed = [f for f in self.futures if f.done()]
        return [(html_from_future(f), self.futures.pop(f)) for f in completed]

    @property
    def status(self):
        d = dict(Counter(f._state for f in self.futures))
        d['FREE'] = self.pool_size - d.get('RUNNING', 0)
        return d



