import io
import numpy as np
import pandas as pd


def prepare_geeklist(csv_pivot, file_geeklist, sep):
    """Use the pivot table to prepare the geeklist.

    Parameters
    ----------
    csv_pivot: str
        The csv file where the pivot table is saved. It must be based on the monthly top 100 only.
    file_geeklist: str
        The file (typically, a ``. txt``) where the geeklist will be saved.
    sep: str
        Separator for the csv files.
    """
    df = pd.read_csv(csv_pivot, sep=sep)
    with io.open(file_geeklist, 'w', encoding='utf-8') as f:
        for index, row in df.iterrows():
            f.write('{}\n'.format(index + 1))
            f.write('{}\n'.format(row['title']))
            f.write('Points: {:.2f}.\n'.format(row['points']))
            f.write('Months in top 100: {}.\n'.format(row['months in top 100']))
            f.write('Months in top 10: {}.\n'.format(row['months in top 10']))
            f.write('Peak position in top 100: {}.\n'.format(row['peak position']))
            # f.write('Average position in top 100: {:.2f}.\n'.format(row['average position in top 100']))
            f.write('"Generalized mean" of position in top 100: {:.2f}.\n'.format(
                (row['points'] / row['months in top 100']) ** (-2)
            ))
            f.write('Current position in top 100: {}.\n'.format(row['current position in top 100']))
            f.write('Months since leaving top 100: {}.\n'.format(row['months since leaving top 100']))
            f.write('Year of Publication: {}.\n'.format(release_date_to_int(row['release_date'])))
            f.write('\n')


def release_date_to_int(release_date):
    if np.isnan(release_date):
        return 'N/A'
    else:
        return str(int(release_date))


if __name__ == '__main__':
    prepare_geeklist(csv_pivot='pivot.csv', file_geeklist='geeklist.txt', sep=';')
