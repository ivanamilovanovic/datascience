import arxivscraper.arxivscraper as ax
import pandas as pd


topics = ['cs','eess','math','physics','q-bio','q-fin','stat']

def scrape_arxiv(topic):
    #scraper = ax.Scraper(category=topic, date_from='2018-02-01', date_until='2018-04-01') #scrape training data
    scraper = ax.Scraper(category=topic, date_from='2018-11-01', date_until='2018-12-01') #scrape testing data
    output = scraper.scrape()
    cols = ('id', 'title', 'categories', 'abstract', 'doi', 'created', 'updated', 'authors')
    df = pd.DataFrame(output, columns=cols)
    return df

if __name__ == "__main__" :
    frames = [scrape_arxiv(topic) for topic in topics]
    result = pd.concat(frames)

    #result.to_csv('TrainingData_feb-march-2018.csv')
    result.to_csv('validation_data_nov_2018.csv')
