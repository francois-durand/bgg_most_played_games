from scrape_data import scrape_data
from exploit_data import exploit_data
from prepare_geeklist import prepare_geeklist
from prepare_extended_table import prepare_extended_table

# TODO For next year
# * Fetch correctly the list of authors for games with multiple authors.
# * Record not only the minimal and maximal number of players, but also the string itself (especially for special cases
#   such as "1, 3-5" for example.
# * Add "rank" to the pivot file.
# * Add column "id thing"?
# * Add column "string"? Such as "[thing=25669][/thing] (240)," for example.
# * Add column "playing_time_avg"?
# * In geeklist, add a line with basic facts about the game, such as #players, duration, etc?
# * Generally speaking, merge csv_pivot with csv_pivot_extended. This will probably lead to a refactoring of
#   scrape_data, exploit_data and prepare_extended_table.
# Prepare the thematic lists (by minimal age, playing time, etc.) automatically.

# Settings

START_YEAR = 2010
START_MONTH = 1
END_YEAR = 2024
END_MONTH = 5  # First month NOT taken into account

CSV_DATA = 'data.csv'
CSV_PIVOT = 'pivot.csv'
CSV_PIVOT_EXTENDED = 'pivot_extended.csv'
FILE_GEEKLIST = 'geeklist.txt'
SEP = ';'  # To be readable by the French version of Excel. If you use the English version: SEP = ','.


def point_function(rank):
    return rank**(-.5)


# Let's go!

scrape_data(start_year=START_YEAR, start_month=START_MONTH, end_year=END_YEAR, end_month=END_MONTH,
            csv_data=CSV_DATA, sep=SEP, n_hundreds=1)

exploit_data(csv_data=CSV_DATA, csv_pivot=CSV_PIVOT, sep=SEP, point_function=point_function)

prepare_geeklist(csv_pivot=CSV_PIVOT, file_geeklist=FILE_GEEKLIST, sep=SEP)

prepare_extended_table(csv_pivot=CSV_PIVOT, csv_pivot_extended=CSV_PIVOT_EXTENDED, sep=SEP)
