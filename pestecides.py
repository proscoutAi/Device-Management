from urllib.request import urlopen

url = 'https://data.gov.il/api/3/action/datastore_search?resource_id=2d741cd4-9c54-492c-8607-933deddb3094&limit=5&q=title:jons'  
fileobj = urlopen(url)
print (fileobj.read())
      