import pandas as pd
from selenium.webdriver import Chrome
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By


def interval_from_str(s, default_value=9999):
    try:
        s = s.replace(', ', '–')
        lst = s.split('–')
        return lst[0], lst[-1]
    except AttributeError:
        return default_value, default_value


def prepare_extended_table(csv_pivot, csv_pivot_extended, sep):
    # Open driver
    driver = Chrome()

    def get_info(xpath, default_value=9999, start=None, end=None):
        try:
            element = driver.find_element(By.XPATH, xpath)
            return element.get_attribute("innerText")[start:end]
        except NoSuchElementException:
            return default_value

    # Open pivot csv
    df = pd.read_csv(csv_pivot, sep=sep)
    list_d_field_value = df.to_dict(orient='records')

    # Scrape data
    for d in list_d_field_value:
        title = d['title']
        print('Fetching additional data for %s' % title)
        url = d['url']
        driver.get(url)
        # Number of players (official)
        n_players_official = get_info(
            '//*[@id="mainbody"]/div[2]/div/div[1]/div[2]/ng-include/'
            'div/ng-include/div/div[2]/div[2]/div[2]/gameplay-module/div/div/ul/li[1]/div[1]',
        )
        n_players_official = n_players_official.replace(" Players", "")
        d['n_players_official_min'], d['n_players_official_max'] = interval_from_str(n_players_official)
        # Number of players (community)
        n_players_community = get_info(
            '//*[@id="mainbody"]/div[2]/div/div[1]/div[2]/ng-include/'
            'div/ng-include/div/div[2]/div[2]/div[2]/gameplay-module/div/div/ul/li[1]/div[2]/span/button/span[2]',
            end=-1
        )
        d['n_players_community_min'], d['n_players_community_max'] = interval_from_str(n_players_community)
        # N players best
        n_players_best = get_info(
            '//*[@id="mainbody"]/div[2]/div/div[1]/div[2]/ng-include/'
            'div/ng-include/div/div[2]/div[2]/div[2]/gameplay-module/div/div/ul/li[1]/div[2]/span/button/span[3]'
        )
        n_players_best = n_players_best.replace("— Best: ", "")
        d['n_players_best_min'], d['n_players_best_max'] = interval_from_str(n_players_best)
        playing_time = get_info(
            '//*[@id="mainbody"]/div[2]/div/div[1]/div[2]/ng-include/'
            'div/ng-include/div/div[2]/div[2]/div[2]/gameplay-module/div/div/ul/li[2]/div[1]/span/span',
            end=-1
        )
        d['playing_time_min'], d['playing_time_max'] = interval_from_str(playing_time)
        d['age_official'] = get_info(
            '//*[@id="mainbody"]/div[2]/div/div[1]/div[2]/ng-include/'
            'div/ng-include/div/div[2]/div[2]/div[2]/gameplay-module/div/div/ul/li[3]/div[1]/span/span'
        )
        d['age_community'] = get_info(
            '//*[@id="mainbody"]/div[2]/div/div[1]/div[2]/ng-include/'
            'div/ng-include/div/div[2]/div[2]/div[2]/gameplay-module/div/div/ul/li[3]/div[2]/span/button/span',
            end=-1
        )
        d['weight'] = get_info(
            '//*[@id="mainbody"]/div[2]/div/div[1]/div[2]/ng-include/'
            'div/ng-include/div/div[2]/div[2]/div[2]/gameplay-module/div/div/ul/li[4]/div[1]/span[2]/span[1]',
            end=-1
        )
        d['game_designer'] = get_info(
            '//*[@id="mainbody"]/div[2]/div/div[1]/div[2]/ng-include/'
            'div/ng-include/div/div[2]/div[2]/div[3]/ng-include/div/ul/li[2]/popup-list/span[2]/a/span',
        )

    # Export to csv
    df = pd.DataFrame(list_d_field_value)
    df.to_csv(csv_pivot_extended, sep=sep, index=False)
