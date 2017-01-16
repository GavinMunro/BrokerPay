import cString
import csv

# http://douglatornell.ca/blog/category/pylons/

def csv_download(self, ...):
    csv_buffer = cStringIO.StringIO()
    csv_writer = csv.writer(csv_buffer)
    header = self._build csv_header(...)
    csv_writer.writerow(header)
    query_result = self.get_data_for_csv(...)
    for result in query_result:
        row = self._build_csv_row(result)
        csv_writer.writerow(row)
    content = csv_buffer.getvalue()
    csv_buffer.close()
    response.content_type = 'text/csv; charset=utf-8'
    response.content_disposition = (
        'attachment; filename="your_file.csv"')
    return content

# To get Excel to play nice with UTF-8 encoded data it's necessary to 
# include 3 specific bytes as a Byte Order Mark (BOM) at the beginning of the file. 
# I did that by prepending them to the heading string for the first column.
def _build_csv_header(self, ...):
    UTF_8_BOM = '\xef\xbb\xbf'
    header = [
        UTF_8_BOM + 'Column 1 Heading',
        # ...
    ]
    return header

# Building the content for each row of the CSV file is just a matter of 
# formatting each query result into an array of strings. Fields containing 
# non-ASCII characters stored as Unicode need to be encoded to UTF-8: 
def _build_csv_row(self, result):
    row = [
        result.column_1_value,
        '{:%Y-%m-%d}'.format(result.some_date),
        # ...
        result.unicode_value.encode('utf-8'),
        # ...
    ]
    return row
