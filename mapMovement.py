#importing all necessary libraries
import pandas as pd
import geopandas
import matplotlib.pyplot as plt
import re
import urllib.request, json
import mplcursors
import matplotlib.patches as mpatches
import numpy as np

#dictionary of colors to use when plotting
colorNames = {0: 'b', 1: 'g', 2: 'r', 3: 'c', 4: 'm', 5: 'y', 6: 'k', 7: 'w', 8:'tab:orange', 9:'tab:gray', 10:'tab:brown' }

#function for cleaning data of Finnish towns and gathering tem to a dictionary
def getTowns(path):
    df = pd.read_csv(path, sep=";")

    #data I used did not transform into .csv correctly in all places, so this looks if the columns accutually contain a working pair of coordinates
    fineCoor = pd.Series(df["Column2"]).str.contains('°N') & pd.Series(df["Column3"]).str.contains('°E')
    df = df[fineCoor]

    #the coordinates were in form xx.xx°X so this removes all but numeric values
    df["coorN"] = pd.to_numeric(df["Column2"].str.split("°", n = 1, expand =  True)[0])
    df["coorE"] = pd.to_numeric(df["Column3"].str.split("°", n = 1, expand =  True)[0])
    towns = df.drop(["Column2", "Column3"], axis = 1)
    
    #there were some identical named towns in the data so this drops all but the first occasion
    towns = towns.drop_duplicates(subset="Column1", keep="first").set_index("Column1")
    return towns.to_dict('index')

#function for finding if a string contains a legimate town, returns it if there is
def matchTown(towns, match):
    for town in towns:
        if town in match:
            return town
    return ""

#same as the last function, but for dates. there is of course other ways of formatting dates, but these probably catch most of the occasions if dealing with Finnish data
def matchDate(match):
    dateDict = dict()
    x = re.search("(\d*\d)[.\-](\d*\d)[.\-](\d\d\d\d)", match)
    if x:
        dateDict["date"] = x.group(1)
        dateDict["month"] = x.group(2)
        dateDict["year"] = x.group(3)
    else: 
        y = re.search("(\d\d\d\d)(?:[-](\d*\d)[-](\d*\d))*", match)
        if y:
            dateDict["date"] = y.group(3)
            dateDict["month"] = y.group(2)
            dateDict["year"] = y.group(1)
    return dateDict

def fixScandicCharacters(word): 
    #Ö
    word = word.replace("Ã–", "%C3%96")
    #ö
    word = word.replace("Ã¶", "%C3%B6")
    #Ä
    word = word.replace("Ã„", "%C3%84")
    #ä
    word = word.replace("Ã¤", "%C3%A4")
    #É
    word = word.replace("Ã‰", "%C3%89")
    #é
    word = word.replace("Ã©", "%C3%A9")
    #Å
    word = word.replace("Ã…", "%C3%85")
    #å
    word = word.replace("Ã¥", "%C3%A5")

    return word

#creates a suitable version of the search words for Finna API
def parseUrl(word):
    separateWords = word.split()
    finishedWord = separateWords[0]
    for i in separateWords[1:]:
        finishedWord += f"%20{i}"

    return finishedWord

#fetches the metadata from Finna
def fetchFinna(wordsToUrl, towns, originalWords, parties):
    metadatas = []

    for search in wordsToUrl:
        pageNumber = 1
        while True:

            #Now finding pictures, but you could change it to photos, although many of the photos are filed as pictures, so would not recommend
            url = f"https://api.finna.fi/api/v1/search?lookfor={search}&type=AllFields&field%5B%5D=institutions&field%5B%5D=summary&field%5B%5D=events&field%5B%5D=subjects&filter%5B%5D=format%3A%220%2FImage%2F%22&sort=relevance%2Cid%20asc&page={pageNumber}&limit=100&prettyPrint=false&lng=fi"
            response = urllib.request.urlopen(url).read()
            data = json.loads(response)
            
            #checks if there are any records in the page, if not moves on
            if "records" in data:
                for i in data["records"]:
                    k = 1
                    matchedTown = matchTown(towns.keys(), str(i))
                    matchedDate = matchDate(str(i))
                    institution = i["institutions"][0]["translated"]
                    if bool(matchedTown) & bool(matchedDate):
                        rowDict = {"Target": originalWords[search], "Date": matchedDate["date"], "Month": matchedDate["month"], "Year": matchedDate["year"], "Town": matchedTown, "Lat": towns[matchedTown]["coorN"], "Lon": towns[matchedTown]["coorE"], "Party": parties[search], "Institution": institution}
                        metadatas.append(rowDict)
                if data["resultCount"] < pageNumber * 100:
                    break
                else:
                    pageNumber += 1
            else:
                break

    return metadatas

#fetches the metadata from Finna API
def getPhotoMetadata(searchwordList, towns):
    #initializing some variables
    wordsToUrl = []
    originalWords = dict()
    parties = dict()
    partiesToNumber = dict()
    index = 0
    party = ""

    #starts reading the searchword list file
    lines = open(searchwordList)
    line = lines.readline()
    
    #lines in the file starting with :: mean that the group is changing. in that case, it addes it to the list of groups
    #otherwise, it creates a searchword for Finna
    while line:
        if "::" not in line:
            word = line
            word = fixScandicCharacters(word)
            finishedWord = parseUrl(word)
            wordsToUrl.append(finishedWord)
            originalWords[finishedWord] = line
            parties[finishedWord] = party
        else:
            party = line.replace(":", "")
            partiesToNumber[party] = index
            index += 1
        line = lines.readline()

    metadatas = fetchFinna(wordsToUrl, towns, originalWords, parties)
    final = pd.DataFrame.from_dict(metadatas)

    #returns the metadata and list of groups
    return final, partiesToNumber

#creates patches to use in legends in the geoplots
def createPatches(labelsLegend, colorsLegend):
    patches = []
    for i,j in zip(labelsLegend, colorsLegend):
        patches.append(mpatches.Patch(color=j, label=i))
    return patches

#i could not find another way to get the hover on the plots to work with mplcursors in multiple pictures at the same time
#other than adding empty rows in the begging so it will annotate those with the old data and the new with correct without overriding the old data
#not the best way probably, but it works for now
def addEmptyRows(data, annLength):
    vector = [0] * annLength
    colorVector = ['w']*annLength

    longs = pd.Series(vector, dtype = float).append(data["Lon"], ignore_index = True)
    lats = pd.Series(vector, dtype = float).append(data["Lat"], ignore_index = True)
    counts = pd.Series(vector, dtype = float).append(data["counts"] * 10, ignore_index = True)
    colors = pd.Series(colorVector, dtype = str).append(data["PartyColor"], ignore_index = True)

    return longs, lats, counts, colors

#visualizes the data so that you can see how many pictures are there in the towns and from which parties they are from
#bigger plot means more pictures, and the color stands for the party which most hits
def drawGeoPlots(data, startYear, endYear):
    annotations = []
    annLength = 0

    for i in range(startYear,endYear + 1):
        #initializes the plot and takes the data which handles the current year the function is dealing with
        fig, ax = plt.subplots(figsize=(20,10))
        year = str(i)
        mask = data["Year"] == str(i)
        currentYear = data[mask]

        #number of hits by party
        partyDivision = currentYear.groupby(["Year", "Town", "Lon", "Lat", "Party"]).size().reset_index(name='partyCounts')

        #creates a dataframe with all the useful information
        size = currentYear.groupby(["Year", "Town", "Lon", "Lat"]).size()
        currentYear = currentYear.groupby(["Year", "Town", "Lon", "Lat"])['Party'].agg(lambda x:x.value_counts().index[0]).to_frame()
        currentYear['PartyColor'] = currentYear['Party'].map(partiesToNumber).map(colorNames)
        currentYear["counts"] = size
        currentYear = currentYear.reset_index()

        if not currentYear.empty:
            #fixes some problems with crs
            longs, lats, counts, colors = addEmptyRows(currentYear, annLength)
            
            #creates legends for featured parties
            labelsLegend = currentYear["Party"].drop_duplicates()
            colorsLegend = currentYear["PartyColor"].drop_duplicates()

            #initializes the plot with the world map
            world = (geopandas.read_file(geopandas.datasets.get_path('naturalearth_lowres')))
            world.plot(ax=ax, color="wheat", edgecolor="black")
            ax.set_facecolor('azure')

            #creates the legends
            patches = createPatches(labelsLegend, colorsLegend)
            plt.legend(handles=patches)

            #plots the datapoints on the map
            im = ax.scatter(longs, lats, s = counts, c = colors)

            #creates the possibility for annotations
            crs = mplcursors.cursor(ax,hover=True)

            #creates the annotations by going through all towns that had hits on the handled year
            for i, txt in enumerate(currentYear["Town"]):
                town = partyDivision[partyDivision["Town"] == txt]
                txt = txt + "\n"
                for idx, row in town.iterrows():
                    txt += f"{row['Party'][0:5]}: {row['partyCounts']}\n"
                annotations.append(txt)
                annLength += 1
            
        #focuses the map to Finland
        ax.set_xlim([10, 40])
        ax.set_ylim([55, 75])

        #makes the annotations hoverable, currently causes error messages, but nothing that breaks the program
        crs.connect("add", lambda sel: sel.annotation.set_text(annotations[sel.target.index]))


#draws a graph for finding out how many hits there every year by party
def drawLineGraph(data, startYear, endYear):
    byTown = data[data["Year"] <= str(endYear)]
    byTown = byTown[byTown["Year"] >= str(startYear)]
    byTown = byTown.groupby(["Year", "Party"]).agg(pd.Series.count).reset_index()
    byTown.set_index('Year', inplace=True)
    byTown.groupby('Party')["Target"].plot(legend = True)
    plt.legend(bbox_to_anchor=(1.04,1), loc="upper left")
    plt.tight_layout()
    plt.show()

#for drawing graph about which institutions have added the picture to finna
def drawInstitutionGraph(data, startYear, endYear):
    dataYear = data[data["Year"] <= str(endYear)]
    dataYear = dataYear[dataYear["Year"] >= str(startYear)]
    groupInstitution = dataYear.groupby("Institution").size().reset_index(name='institutionCounts')
    x = groupInstitution["Institution"]
    y = groupInstitution["institutionCounts"]
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.set_xticks(np.arange(len(x)))
    ax.set_xticklabels(x, rotation = 90)
    ax.bar(x, y)
    fig.tight_layout()

#for plotting how diversely politician are present in different institutions
def institutionsPoliticians(data, startYear, endYear):
    dataYear = data[data["Year"] <= str(endYear)]
    dataYear = dataYear[dataYear["Year"] >= str(startYear)]
    s = pd.crosstab(dataYear['Institution'], dataYear['Party']).apply(lambda r: r/r.sum(), axis=1)
    s.plot.bar(stacked=True)
    plt.legend(bbox_to_anchor=(1.04,1), loc="upper left")
    plt.tight_layout()
    plt.show()
    
#for showing in how many pictures politicians were in
def politicianCount(data, startYear, endYear):
    dataYear = data[data["Year"] <= str(endYear)]
    dataYear = dataYear[dataYear["Year"] >= str(startYear)]
    politicianN = dataYear.groupby("Target").size().reset_index(name="PoliticianCount")
    politicianN = politicianN.sort_values(by="PoliticianCount", ascending=False)
    fig, ax = plt.subplots()
    y_pos = np.arange(len(politicianN["Target"]))
    ax.barh(y_pos, politicianN["PoliticianCount"], align='center')
    ax.set_yticks(y_pos)
    ax.set_yticklabels(politicianN["Target"])
    ax.invert_yaxis()

#actually runs the program
#the program runs quite a while, but i think that is mostly because of the multiple queries you have to make to Finna

townList = input("Enter the path to your town list: ")
searchwordList = input("Enter the path to your searchword list: ")
start = input("Enter start year: ")
end = input("Enter end year: ")

print("Please wait. This may take a while, especially if your searchword list is very long.")
print('...')

#My location tl: C:\Users\mikko\OneDrive\Työpöytä\YliopistoB\Elements - Digi\CompLitProj\Kunnat.csv
#C:\Users\mikko\OneDrive\Työpöytä\YliopistoB\Elements - Digi\CompLitProj\KansanedustajatTesti.txt
#My location swl1: C:\Users\mikko\OneDrive\Työpöytä\YliopistoB\Elements - Digi\CompLitProj\Kansanedustajat1972.txt
#My location swl2: C:\Users\mikko\OneDrive\Työpöytä\YliopistoB\Elements - Digi\CompLitProj\Kansanedustajat1991.txt
result, partiesToNumber = getPhotoMetadata(searchwordList, getTowns(townList))
result.to_csv(r"C:\Users\mikko\OneDrive\Työpöytä\YliopistoB\Elements - Digi\CompLitProj\dataframe1991.csv")
result = result.drop_duplicates()
institutionsPoliticians(result, int(start), int(end))
drawLineGraph(result, int(start), int(end))
drawInstitutionGraph(result, int(start), int(end))
drawGeoPlots(result, int(start), int(end))
politicianCount(result, int(start), int(end))


#shows the plots
plt.show()

