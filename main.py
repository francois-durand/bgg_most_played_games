from scrape_data import scrape_data
from exploit_data import exploit_data
from prepare_geeklist import prepare_geeklist

# Settings

START_YEAR = 2010
START_MONTH = 1
END_YEAR = 2021
END_MONTH = 5  # First month NOT taken into account

CSV_DATA = 'data.csv'
CSV_PIVOT = 'pivot.csv'
FILE_GEEKLIST = 'geeklist.txt'
SEP = ';'  # To be readable by the French version of Excel. If you use the English version: SEP = ','.


def point_function(rank):
    return rank**(-.5)


# Let's go!

scrape_data(start_year=START_YEAR, start_month=START_MONTH, end_year=END_YEAR, end_month=END_MONTH,
            csv_data=CSV_DATA, sep=SEP, n_hundreds=1)

exploit_data(csv_data=CSV_DATA, csv_pivot=CSV_PIVOT, sep=SEP, point_function=point_function)

prepare_geeklist(csv_pivot=CSV_PIVOT, file_geeklist=FILE_GEEKLIST, sep=SEP)
