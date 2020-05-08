import io
import pandas as pd


def prepare_geeklist(csv_pivot, file_geeklist, sep):
    """Use the pivot table to prepare the geeklist.

    Parameters
    ----------
    csv_pivot: str
        The csv file where the pivot table is saved.
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
            f.write('Average position in top 100: {:.2f}.\n'.format(row['average position in top 100']))
            f.write('Year of Publication: {}.\n'.format(row['release_date']))
            f.write('\n')
