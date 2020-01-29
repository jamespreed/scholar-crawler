#from requests_html import HTMLSession
from time import sleep
from random import lognormvariate
from collections import Counter
from .firefox import FirefoxSession
from .graph import AuthorGraph
from .requests import AuthorSearch


class ScholarQueue:
    def __init__(self, 
                 max_hops=1, 
                 sleep_between=True,
                 max_author_search_page=3,
                 max_author_page=2):
        #self.sess = HTMLSession()
        self.sess = FirefoxSession()
        self.max_hops = max_hops
        self.sleep_between = sleep_between
        self.max_author_search_page = max_author_search_page
        self.max_author_page = max_author_page
        self.set_sleep()
        self.request_queue = []
        self.author_graph = AuthorGraph()
        self.active_request = None
        self.active_response = None

        # initialize cookies, check for captcha
        self.sess.get('https://scholar.google.com')

    def __repr__(self):
        r = len(self.request_queue)
        s = self.sleep_between
        return f'<ScholarQueue request_queue=[{r} requests], sleep={s}>'

    def set_sleep(self, mu=1, sigma=.3, divisor=10):
        """
        Sets the parameters for the lognoramvariate random distribuion used 
        for sleep.

        t_sleep = lognormvariate(mu, sigma) / divisor
        """
        self._mu = mu
        self._sigma = sigma
        self._div = divisor

    @property
    def status(self):
        c = Counter([r._name for r in self.request_queue])
        s = f'ScholarQueue: {len(self.request_queue)} requests in queue\n'
        s += '\n'.join([f'  - {k}: {v}' for k, v in c.items()])
        return s

    def get_next(self):
        """
        Pops the next request from the queue and a request/response pair
        for each url in the request object
        """
        if self.sleep_between:
            t = lognormvariate(self._mu, self._sigma) / self._div
            sleep(t)
        self.active_request = request = self.request_queue.pop(0)
        for url in request.urls:
            self.active_response = response = self.sess.get(url)
            # check for robot detection, alert user
            if self._check_for_robot():
                ans = input('Google has detected a robot.  Do you want to solve the captcha? ([y]/n):')
                self._input_handler(ans)
            response.html.lxml.url = url
            yield request, response

    def _input_handler(self, ans):
        if (not ans) or (ans.lower()[0]=='y'):
            self.sess.show()
            input('Press any key to continue...')
        else:
            raise KeyboardInterrupt('User chose to stop the crawl.')

    def _check_for_robot(self):
        """
        Checks to see if google has detected that we are scraping
        """
        msgs = [
            b'Our systems have detected unusual traffic from your computer network',
            b"Please show you're not a robot",
            b"Sorry, we can't verify that you're not a robot",
            b"really you sending the requests, and not a robot"
        ]
        return any(msg in self.active_response.content for msg in msgs)

    def search_authors(self, author_str, verbose=None):
        """
        Begins a crawl using the author search for `author_str`
        AuthorSearch >> Author >> TitleSearch >> [Document :+: [Author]]
        """
        auth_search = AuthorSearch.from_author_string(author_str)
        auth_search.max_page = self.max_author_search_page
        self.request_queue.append(auth_search)
        self.crawl(verbose=verbose)

    def process_response(self, request, response, verbose=False):
        """
        Uses the request to parse the response.html.lxml and add the results to
        the `author_graph`.
        """
        # need to track the hops here
        # check if auther/paper is already in the graph
        hop = request.hop
        
        # handle Document objects separately
        if request._name == 'TitleSearch':
            document = request.parse(response.html.lxml)
            new_authors = self.author_graph.add_publication(document)
            if verbose: 
                print(f'-- Document {document.doc_id}:> added to graph')

            for author in new_authors:
                self.request_queue.append(author)
            if verbose: 
                print(f'-- Document :> {len(new_authors)} Authors added to queue')
            return

        # stops parsing documents if the Author is the last hop
        if request._name == 'Author':
            if hop >= self.max_hops:
                request.max_page = 0

        # parse the result to get the next set of request objects
        new_requests = request.parse(response.html.lxml)
        for new_req in new_requests:
            self.request_queue.append(new_req)
        
        if verbose and new_requests: 
            # not exactly correct, but close enough...
            print(f'-- {request._name} :> {len(new_requests)} {new_req._name} added to queue')

    def crawl(self, steps=0, verbose=None):
        """
        Begins the crawling process.

        :steps: [int] How many requests to crawl.  Use 0 for continuous crawling
        :verbose: [None, True, False, 'v-', 'vv', '-v'] Sets the verbosity level
        """
        if verbose not in (None, True, False, 'v-', 'vv', '-v'):
            raise ValueError('verbose must be None, True, False, `v-`, `vv`, or `-v`.')
        if verbose is None or verbose==False:
            v1 = v2 = False
        elif verbose==True:
            v1 = v2 = True
        else:
            v1, v2 = verbose[0]=='v', verbose[1]=='v'
        if v1:
            print('Begining crawl:')
        i = 1
        while True:
            for request, response in self.get_next():
                self.process_response(request, response, v2)
            if v1:
                print(f'({i}) Queue Status :> {len(self.request_queue)} pending requests')
            if steps and i>=steps:
                break
            i += 1

# result parser for next button...
    # res = sess.get('https://scholar.google.com/citations?hl=en&view_op=search_authors&mauthors=unimi.it')
    # if res.status_code == 200:
    #     _next = (
    #         res.html.find('button[@aria-label="Next"]', first=True)
    #                 .attrs.get('onclick', '')
    #                 .replace("'",'')
    #                 .split('=')[-1]
    #                 .encode('latin1')
    #                 .decode('unicode-escape')
    #     )
    #     res._next = res.html._make_absolute(_next) if _next else None
