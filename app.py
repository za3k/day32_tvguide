#!/bin/python3
import flask, flask_login
from flask import url_for, request, render_template, redirect
from flask_login import current_user
import collections, json, queue, random, functools, urllib.parse, re
from datetime import datetime,timedelta
from base import app,load_info,ajax,DBDict,DBList,random_id,hash_id,full_url_for
from bs4 import BeautifulSoup
import requests

# -- Info for every Hack-A-Day project --
load_info({
    "project_name": "Hack-A-TV-Guide",
    "source_url": "https://github.com/za3k/day33_tvguide",
    "subdir": "/hackaday/tvguide",
    "description": "A TV guide generated from wikipedia.",
    "instructions": "",
    "login": False,
    "fullscreen": True,
})

# -- Routes specific to this Hack-A-Day project --
episodes = DBDict("episodes")
shows = DBDict("show")

@app.route("/")
@app.route("/p/<int:page>")
def index(page=0):
    return index_letter("A", page)

@app.route("/<letter>")
@app.route("/<letter>/p/<int:page>")
def index_letter(letter, page=0):
    shows = categories_starting_with(letter)[page:page+102]
    
    prev, next = None, None
    if page >= 100:
        prev = url_for("index_letter", letter=letter, page=page-100)
    if len(shows) >= 100:
        next = url_for("index_letter", letter=letter, page=page+100)

    return render_template('index.html', shows=shows, page=page, prev=prev, next=next)

@app.route("/show/<show>")
def view_show(show):
    show = crawl_show(show)
    return render_template('show.html', show=show)

# --- Crawling ---
wiki_cache = DBDict("cache")
func_cache = DBDict("func_cache")
categories = DBDict("category")

BLACKLIST = {
    "Category:Television_characters_by_genre",
}
class CrawlQueue():
    def __init__(self, init=[]):
        self.known = set()
        for x in init:
            self.add(x)
    def add(self, x: str):
        if x in self.known: pass
        if x in BLACKLIST: pass
        self.known.add(x)
    def extend(self, new):
        for x in new:
            self.add(x)
    def __len__(self):
        return len(self.known)
    def __iter__(self):
        crawled = set()
        new = True
        while new:
            new = False
            for x in list(self.known):
                if x not in crawled:
                    crawled.add(x)
                    yield x
                    new = True

def cached(f):
    @functools.wraps(f)
    def f2(*args):
        key = f.__name__ +"("+", ".join(map(repr, args))+")"
        if key in func_cache:
            r = func_cache[key]
            #if r["last_crawled"] >= (datetime.today() - timedelta(days=30)):
            return r["content"]
        r = f(*args)
        func_cache[key] = {
            "last_crawled": datetime.now(),
            "content": r,
        }
        return r
    return f2

def categories_starting_with(l):
    l = l.upper()
    all = crawl_categories()
    r = []
    for x in all:
        if x.startswith(l) or x.startswith(l.lower()):
            r.append(x)
    return sorted(r)

def getWikipediaPage(page):
    r = wiki_cache.get(page)
    if r and r["last_crawled"] >= (datetime.today() - timedelta(days=1)):
        return r["content"]
    url = "https://en.wikipedia.org/wiki/{}".format(page)
    wiki_cache[page] = {
        "content": requests.get(url).content,
        "last_crawled": datetime.now(),
    }
    return wiki_cache[page]["content"]

def crawl_category(page):
    content = getWikipediaPage(page)
    soup = BeautifulSoup(content, 'html.parser')
    categories = [a.get("href").split("/")[-1] for a in soup.select('#mw-subcategories a')]
    categories = [x for x in categories if "series" in x and "series)" not in x and "index.php" not in x]
    pages = [a.get("href").split("/")[-1] for a in soup.select('#mw-pages a')]
    return {
        "parsed": soup.prettify(),
        "categories": categories,
        "shows": pages,
    }

def unwiki(x):
    return urllib.parse.unquote(x).replace("_", " ")
app.jinja_env.filters["urldecode"] = urllib.parse.unquote
app.jinja_env.filters["unwiki"] = unwiki

def crawl_show(page):
    content = getWikipediaPage(page)

    # Is it even a TV show? If not, abort early.
    name = urllib.parse.unquote(page).replace("_", " ")
    NOT_A_SHOW = {"show": False, "name": name, "episodes": "", "url": "https://en.wikipedia.org/wiki/"+page}
    if b"Infobox_television" not in content: return NOT_A_SHOW
    soup = BeautifulSoup(content, 'html.parser')

    # Grab info from the infobox
    infobox = soup.select_one("table.infobox")
    if not infobox: return NOT_A_SHOW
    info = {}
    for row in infobox.select("tr"):
        label = row.find("th")
        value = row.find("td")
        if not label or not value: continue
        label = label.get_text()
        info[label] = value.get_text()
        

    # Parse episodes
    REPLACE = {
        'No.overall': "ep_total",
        'No. inseason': "episode",
        'No.': "episode",
        'Title': "title",
        'Directed by': "director",
        'Written by': "writer",
        'Original air date': "date",
        'Original release date': "date",
        'Prod.code': "code",
    }
    def header_replace(x):
        x = re.sub(r"\[.*\]|\u200a", "", x)
        return REPLACE.get(x, x)
    def parse_episode_header(row):
        return [header_replace(td.get_text()) for td in row.select("th")]
    def parse_episode_row(header, row):
        ep = {}
        for header, td in zip(header, row.select("th,td")):
            ep[header] = td.get_text()
        return ep
    seasons = []

    # Check whether the episodes are on this page or a separate page
    episode_tables = soup.select(".wikiepisodetable")
    # If another page, download it and parse them
    if len(episode_tables) == 0:
        for a in infobox.select("a"):
            if "list of episodes" in a.get_text():
                ep_page = a.get("href").split("/")[-1]

                content_eps = getWikipediaPage(ep_page)
                soup_eps = BeautifulSoup(content_eps, 'html.parser')
                episode_tables = soup_eps.select(".wikiepisodetable")
                break

    # If this page, parse them.
    for episode_table in episode_tables:
        season_name = "Season ?"
        label = episode_table.find_previous("h3")
        if label:
            season_name = label.get_text().replace("[edit]","")

        m = re.match("Season ([0-9]+)", season_name)
        season_num = "?"
        if m:
            season_num = m.group(1)

        rows = episode_table.select("tr:not(.expand-child)")
        header = parse_episode_header(rows[0])
        #print(season_name)
        #print(header)
        #print(parse_episode_row(header, rows[1]))
        episodes = [parse_episode_row(header, row) for row in rows[1:]]
        for ep in episodes:
            ep["season"] = season_num
        season = {
            "name": season_name,
            "episodes": episodes,
        }
        seasons.append(season)
        
    return {
        "show": True,
        "seasons": seasons,
        "name": name,
        "info": info,
        "url": "https://en.wikipedia.org/wiki/"+page,
    }

@cached
def crawl_categories():
    _categories = CrawlQueue(["Category:Television_series_by_genre"])
    _shows = CrawlQueue()
    for i, category in enumerate(_categories):
        r = crawl_category(category)
        _categories.extend(r["categories"])
        _shows.extend(r["shows"])
        print(i+1, "/", len(_categories), category)
    return sorted(_shows)

@app.route("/crawl/all")
def crawl_all():
    def generate():
        _shows = crawl_categories()
        yield "About to crawl {} shows.\n\n".format(len(_shows))
        for i, show in enumerate(_shows):
            try:
                r = crawl_show(show)
                shows[show] = r
                yield "Crawled {}/{} {}\n".format(i+1, len(_shows), show)
            except Exception:
                yield "Failed {}/{} {}\n".format(i+1, len(_shows), show)
            #episodes.update(r["episodes"])
    return flask.Response(generate(), mimetype="text/plain")
