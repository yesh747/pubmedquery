#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sandboxing with pubmed api

Created on Wed Mar 17 19:08:14 2021

@author: yesh
"""
import time
import requests
import xml.etree.ElementTree as xml
import pickle


class PubMedArticle():
    def __init__(self, article_xml, print_xml=False):
        # get article

        self.root = article_xml
        
        # initialize citedByPMIDs
        self.citedByPMIDs = None
        
        if print_xml:
            self.print_xml(self.root)
        try:
            self.pmid = self.root.find('./MedlineCitation/PMID').text
            articlePath = './MedlineCitation/Article/'
                
            # METADATA
            self.journal = self.root.find(articlePath + 'Journal/Title').text
            self.journal_abbr = self.root.find(articlePath + 'Journal/ISOAbbreviation').text
            self.pubtype = self.root.find(articlePath + 'PublicationTypeList/PublicationType').text
            
            # DATE
            pubdate = self.root.find('./PubmedData/History/PubMedPubDate[@PubStatus="pubmed"]')
            year = pubdate.find('Year').text
            month = pubdate.find('Month').text
            day = pubdate.find('Day').text
            
            self.pubdate = {'year': year, 'month': month, 'day': day}
            
            self.title = self.root.find(articlePath + 'ArticleTitle').text
            
            # abstract
            self.abstract = self.root.findall('.//AbstractText')
            # need this step for when there are multiple abstract text objects
            self.abstract = ' '.join([''.join(section.itertext()) for section in self.abstract])
            
            # authors
            authorlist = self.root.findall(articlePath + 'AuthorList/Author')
            self.authors = []
            for author in authorlist:        
                affiliation_xml = author.find('AffiliationInfo/*')
                if affiliation_xml is not None:
                    affiliation = ''.join(author.find('AffiliationInfo/*').itertext())
                else:
                    affiliation = None
                    
                # A Group or Collective is sometimes included in author lists instead of an author
                collective_name = author.find('CollectiveName')
                if collective_name is not None:
                    self.collective_name = collective_name.text
                else:
                    
                    # check if they have firstname
                    firstname_xml = author.find('ForeName')
                    if firstname_xml is not None:
                        firstname = firstname_xml.text
                    else:
                        firstname = None
                    
                    self.authors.append({
                        'lastname': author.find('LastName').text,
                        'firstname': firstname,
                        'affiliation': affiliation,
                        })
                    
        except AttributeError:
            self.print_xml(self.root)
            print(self.title)
            print(self.journal)
            print(self.pmid)
            raise(AttributeError)
            
    def add_citedByData(self, citedByPMIDs):
        self.citedByPMIDs = citedByPMIDs
        return
        
    def print_xml(self, xml_item=None):
        if xml_item==None:
            xml_item = self.root
        print(xml.tostring(xml_item, encoding='utf8').decode('utf8'))


class PubMedArticleList():
    """
    - Input: list of pmids     
    - Creates Object is list of PubMedArticles
    """
    def __init__(self, pmids, BASE_URL, DB,  print_xml=False):
        # A. Get articles
        url = '{}efetch.fcgi?db={}&id={}&retmode=xml'.format(BASE_URL, DB, pmids)
        r = requests.get(url)
        r.raise_for_status()
        root = xml.fromstring(r.text)
        time.sleep(0.34)
        

        self.root = root
        self.articles_xml = root.findall('./PubmedArticle')
        self.articles = []
        for article_xml in self.articles_xml:
            self.articles.append(PubMedArticle(article_xml, print_xml=print_xml))
          
        # B. Get articles that cite the queried articles.
        linkname =  '{}_pubmed_citedin'.format(DB)
        link_url = '{}/elink.fcgi?dbfrom={}&linkname={}&id={}&retmode=json'.format(
            BASE_URL, 
            DB, 
            linkname,
            '&id='.join(pmids))
        r_link = requests.get(link_url)
        r_link.raise_for_status()
        r_link = r_link.json()
        linksets = r_link['linksets']
        time.sleep(0.34)     
        
        # looping through nonsense to get to the IDs for articles that cite the PMID articles
        for linkset in linksets:
            linkset_pmid = linkset['ids'][0]
            assert(len(linkset['ids']) == 1)
            if 'linksetdbs' in linkset.keys():
                for linksetdb in linkset['linksetdbs']:
                    if (linksetdb['linkname'] == linkname) and ('links' in linksetdb.keys()):
                        links = linksetdb['links']
                        citedByPMIDs = links
                        for article in self.articles:
                            if article.pmid == linkset_pmid:
                                article.add_citedByData(citedByPMIDs)
                                    
                            
            
            



class PubMedQuery():
    def __init__(self, query,
                 BASE_URL='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/', 
                 DB='pubmed',
                 RESULTS_PER_QUERY=100000,
                 citedBy=True, # get articles that cite the queried articles - will slow down queries 
                 print_xml=False):
        self.BASE_URL = BASE_URL
        self.DB = DB
        self.RESULTS_PER_QUERY = RESULTS_PER_QUERY
        self.query = query
        self.citedBy=citedBy
        
        # query
        self.pmids, self.count, self.querytranslation = self.__query_pmids__(self.query)
        print('{} results for: {}'.format(self.count, self.querytranslation))

        self.articles = self.__query_articles__(self.pmids, print_xml)
        
        
    def __query_pmids__(self, query):
        pmids = []
        retstart = 0
        count = 999999
        
        while retstart < count:  
            url = '{}esearch.fcgi?db={}&term={}&retmax={}&retmode=json&retstart={}'.format(
                    self.BASE_URL, self.DB, self.query, self.RESULTS_PER_QUERY, retstart)
            r = requests.get(url)
            r.raise_for_status()
            r = r.json()['esearchresult']
            querytranslation = r['querytranslation']
            retstart = retstart + self.RESULTS_PER_QUERY
            count = int(r['count'])
            pmids = pmids + r['idlist']
            time.sleep(0.34)    
            
                        
        return pmids, count, querytranslation
             
    def __chunk__(self, lst, n):
        """Yield successive n-sized chunks from lst."""
        return [lst[i:i + n] for i in range(0, len(lst), n)]
    
    def __query_articles__(self, pmids, print_xml):
        count = len(pmids)
        articles = []
        pmids = self.__chunk__(pmids, min(200, self.RESULTS_PER_QUERY))
        i = 0
        for pmid_chunk in pmids:
            i += len(pmid_chunk)
            print('\rGetting data on {}/{} articles'.format(i, count), end='')
            
            articleList = PubMedArticleList(pmid_chunk, self.BASE_URL, self.DB, print_xml)
            articles = articles + articleList.articles
            

        return articles
    
    
if __name__ == '__main__':
    
    
    # using cited by will slow querying down to 3 articles/second because you have to find all the articles that cite the original article
    
    t0 = time.time()
    query = PubMedQuery('("Head Neck"[Journal])',)
    print('Time to Run Query: {}'.format(time.time() - t0))
    
    
    
    for article in query.articles:
        print('-'*75)
        print(article.title)
        print(article.citedByPMIDs)

        # print(article.abstract)
        # print(article.pubdate)
        # print(article.authors)

    
    
    
    
    
    
    