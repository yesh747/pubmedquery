#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sandboxing with pubmed api

Created on Wed Mar 17 19:08:14 2021

@author: yesh
"""
import os

import time
import numpy as np
import pandas as pd
import requests
import xml.etree.ElementTree as xml

from datetime import date


class PubMedArticle():
    def __init__(self, article_xml, print_xml=False):
        # get article

        self.root = article_xml
        
        # initialize citedByPMIDs
        self.citedByPMIDs = []
        
        if print_xml:
            self.print_xml(self.root)
        try:
            self.pmid = self.root.find('./MedlineCitation/PMID').text
            articlePath = './MedlineCitation/Article/'
                
            # METADATA
            self.journal = self.root.find(articlePath + 'Journal/Title').text
            self.journal_abbr = self.root.find(articlePath + 'Journal/ISOAbbreviation').text
            self.pubtypes = [pubtype.text for pubtype in self.root.findall(articlePath + 'PublicationTypeList/PublicationType')]

            journal_issue_xml = self.root.find(articlePath + 'Journal/JournalIssue/Issue')
            if journal_issue_xml is not None:
                self.journal_issue = self.root.find(articlePath + 'Journal/JournalIssue/Issue').text
            else:
                self.journal_issue = None
                
            journal_volume_xml = self.root.find(articlePath + 'Journal/JournalIssue/Volume')
            if journal_volume_xml is not None:
                self.journal_volume = self.root.find(articlePath + 'Journal/JournalIssue/Volume').text
            else:
                self.journal_volume = None
            
            # DATE
            pubdate = self.root.find('./PubmedData/History/PubMedPubDate[@PubStatus="pubmed"]')
            year = pubdate.find('Year').text
            month = pubdate.find('Month').text
            day = pubdate.find('Day').text
            
            self.pubdate = date(int(year), int(month), int(day))
            
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
                    
            # Keywords
            keywordlist = self.root.findall(articlePath + '../KeywordList/Keyword')
            self.keywords = []
            for keyword in keywordlist:
                self.keywords.append(keyword.text)
                
                
            # MAJOR Mesh headings
            meshheading_major_list = self.root.findall(articlePath + '../MeshHeadingList/MeshHeading/*[@MajorTopicYN="Y"]')
            self.meshheadings_major = []
            for meshheading_major in meshheading_major_list:
                self.meshheadings_major.append(meshheading_major.text)    
            # - remove duplicates
            self.meshheadings_major = list(dict.fromkeys(self.meshheadings_major))


            # MINOR mesh headings
            meshheading_minor_list = self.root.findall(articlePath + '../MeshHeadingList/MeshHeading/*[@MajorTopicYN="N"]')
            self.meshheadings_minor = []
            for meshheading_minor in meshheading_minor_list:
                self.meshheadings_minor.append(meshheading_minor.text) 
            # - remove duplicates
            self.meshheadings_minor = list(dict.fromkeys(self.meshheadings_minor))
            
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
    - Creates Object that is a list of PubMedArticles
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
            
        print('\n')
        return articles
    
    
if __name__ == '__main__':
    
    journals = ['Am J Otolaryngol',
                'Clin Otolaryngol',
                'Ear and hearing',
                'Ear Nose Throat J',
                'Eur Arch Otorhinolaryngol',
                'Head Neck',
                'Int Forum Allergy Rhinol',
                'Int J Pediatr Otorhinolaryngol',
                'JAMA Facial Plast Surg',
                'JAMA Otolaryngol Head Neck Surg', 
                'J Assoc Res Otolaryngol',
                'J Voice',
                'J Laryngol Otol',
                'J Neurol Surg B Skull Base',
                'Laryngoscope', 
                'Laryngoscope Investig Otolaryngol'
                'Oral Oncol',
                'Otolaryngol Clin North Am',
                'Otol Neurotol',
                'Otolaryngol Head Neck Surg',
                'Rhinology', 
                ]
    query_text = '("' + '"[Journal]) OR ("'.join(journals) + '"[Journal])'
    
    t0 = time.time()
    query = PubMedQuery(query_text)
    print('\nTime to Run Query: {:2f}min'.format((time.time() - t0)/60))
    
    
    i=0
    author_list = []
    firstname_list = []
    for article in query.articles:
        print('-'*75)
        print(article.title)
        print(article.citedByPMIDs)
        print(article.keywords)
        print(article.meshheadings_major)
        print(article.meshheadings_minor)
        print(article.pubdate)
        print(article.authors)
        for author in article.authors:
            if not author['firstname']:
                continue
            if len(author['firstname']) > 1:
                author_list.append('{} {}'.format(author['firstname'], author['lastname']))
                firstname_list.append('{}'.format(author['firstname']))

        # print(article.abstract)
              
        # count single authors pubs
        if len(article.authors) == 1:
            for author in article.authors:
                if author['firstname'] == None:
                    continue
                if len(author['firstname'].split(' ')[0]) > 1:
                    print('{} {}'.format(author['firstname'], author['lastname']))
                    i+=1                 
    print(i)
    print(len(np.unique(author_list)))
    
    
    
    
    
    
    # SEE HOW MANY FIRSTNAMES ARE IN OUR DATABASE
    # PARAMS
    DATADIR = '../name_classifier/data'
    
    
    # 1. Load data
    data_fps = [os.path.join(DATADIR,file) for file in os.listdir(DATADIR) if file.endswith('.txt')]
    
    colnames = ['name', 'sex', 'freq']
    df = pd.DataFrame(columns=colnames)
    for fp in data_fps:
        df_sub = pd.read_csv(fp, header=None)
        df_sub.columns = colnames
        df = df.append(df_sub)
        
    # - convert sex to binary
    df['sex'] = np.where(df['sex'] == 'M', 1, 0)
        
    # - drop repeats
    df = df.groupby(['name', 'sex'], as_index=False).agg('sum')
    
    # - count how many male only and how many female only
    female_names = df[df['sex'] == 0]['name'].str.lower()
    male_names = df[df['sex'] == 1]['name'].str.lower()
    both_names = np.intersect1d(female_names, male_names)
    female_names = set(both_names) ^ set(female_names)
    male_names =  set(both_names) ^ set(male_names)
    
    print('Only {} ({:.2f}%) names are both male and female'.format(len(both_names),
                                                           100*len(both_names)/len(np.unique(df['name']))))
    
    i = 0
    for name in np.unique(firstname_list):
        name = name.split(' ')[0]
        if name.lower() in male_names:
            i += 1
        elif name.lower() in female_names:
            i += 1
        else:
            print(name)
            
    print(i/len(np.unique(firstname_list)))

    
    
    
    
    
    
    