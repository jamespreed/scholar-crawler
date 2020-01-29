# Scholar Crawler
A work in progress.  It is designed to crawl through Google Scholar and build networks of co-authorship.

## Installation
Clone or download the repo, it runs from source.  
For cloning via HTTP: `git clone https://github.com/jamespreed/scholar-crawler.git`
For cloning via SSH: `git clone git@github.com:jamespreed/scholar-crawler.git`

## Requirements
Because of captchas, this runs using selenium and Firefox, so you must have Firefox installed.  This is currently designed for Windows, but the only  Feel free to use the browser of your choice, you will need to roll your own session class.

Here is a Conda environment file (copy and save it as `scholar.yaml`) you can use to create an environment via `conda env create -n scholar -f scholar.yaml`
```
name: scholar
channels:
- defaults
- conda-forge
dependencies:
- python=3.7.*
- pywin32=227  # [win]
- selenium=3.14.0
- geckodriver=0.26.0
- lxml=4.4.2
- urllib3=1.25.8
```

## Usage
While still in alpha, this needs to be run in interactive mode.  Or you can build your own scripts.  

```
from scholar_crawler import ScholarQueue

sq = ScholarQueue()  # launches Firefox
sq.search_authors('some dude')  # 
sq.crawl()
```