import calendar
import pandas as pd
from selenium.webdriver import Chrome
from selenium.common.exceptions import NoSuchElementException


def month_year_iter(start_year, start_month, end_year, end_month):
    ym_start = 12*start_year + start_month - 1
    ym_end = 12*end_year + end_month - 1
    for ym in range(ym_start, ym_end):
        y, m = divmod(ym, 12)
        yield y, m+1


def scrape_data(start_year, start_month, end_year, end_month, csv_data, sep):
    """Scrape data on BGG and export to csv.

    Parameters
    ----------
    start_year: int
        Start year.
    start_month: int
        Start month.
    end_year: int
        End year.
    end_month: int
        First month NOT taken into account.
    csv_data: str
        The csv file where the data will be saved.
    sep: str
        Separator for the csv file.
    """
    # Open driver
    driver = Chrome()

    # Scrape main data
    list_d_field_value = []
    for year, month in month_year_iter(start_year, start_month, end_year, end_month):
        print('Scraping year %s, month %s' % (year, month))
        _, last_day = calendar.monthrange(year, month)
        start_date = "{}-{:02d}-01".format(year, month)
        end_date = "{}-{:02d}-{}".format(year, month, last_day)
        url = "https://boardgamegeek.com/plays/bygame/subtype/boardgame/start/%s/end/%s?sortby=distinctusers" % (
            start_date, end_date)
        driver.get(url)
        for i in range(100):
            element = driver.find_element_by_xpath('//*[@id="maincontent"]/table/tbody/tr[%s]/td[1]/a' % (i + 2))
            text = element.get_attribute('text')
            url = element.get_attribute('href')
            list_d_field_value.append({'year': year, 'month': month, 'position': i + 1, 'title': text,
                                       'url': url})

    # Scrape release dates
    titles_urls = {(d_field_value['title'], d_field_value['url']) for d_field_value in list_d_field_value}
    d_url_release = {}
    for title, url in sorted(titles_urls):
        print('Fetching release date for %s' % title)
        driver.get(url)
        try:
            element = driver.find_element_by_xpath('//*[@id="mainbody"]/div/div[1]/div[1]/div[2]/ng-include/'
                                                   'div/ng-include/div/div/div[2]/div[1]/div/div[2]/h1/span')
            release_date = element.get_attribute("innerText")[1:5]
        except NoSuchElementException:  # For "Unfinished prototype", there is no date
            release_date = ''
        d_url_release[url] = release_date

    # Close driver
    driver.close()

    # Include release dates into main data
    for d_field_value in list_d_field_value:
        url = d_field_value['url']
        release_date = d_url_release[url]
        d_field_value['release_date'] = release_date

    # Export to csv
    df = pd.DataFrame(list_d_field_value, columns=['year', 'month', 'position', 'title', 'url', 'release_date'])
    df.to_csv(csv_data, sep=sep, index=False)
