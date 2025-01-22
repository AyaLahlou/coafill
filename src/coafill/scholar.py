from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Tuple, List

from scholarly import scholarly
from tqdm import tqdm

if TYPE_CHECKING:
    from scholarly.data_types import Author, Publication

def get_scholar_info(name: str) -> str:
    try:
        # Search for the author
        search_query = scholarly.search_author(name)
        author = next(search_query) # type: ignore
        
        # Extract Google Scholar ID and affiliation
        affiliation = author.get('affiliation', 'No affiliation listed') if 'affiliation' in author else ''
        
        return affiliation
    except StopIteration:
        return ""
    except Exception as e:
        return f"An error occurred: {str(e)}"

def get_coauthors(
    scholar_id: str = "1KXRphAAAAAJ",
    years_back: int | None = 4,
    filename: str | Path | None = "coauthors.csv",
) -> list[str]:
    """
    Given a Google Scholar ID, return a list of coauthors from the past N years.

    Parameters
    ----------
    scholar_id : str
        Google Scholar ID of the author. This is the string of characters
        that appears in the URL of the author's Google Scholar profile
        immediately after "user=" and before "&hl=".
    years_back : int | None
        Number of years to look back for coauthors. Set to `None` for no limit.
    filename : str | Path | None
        Path to the CSV file to write to, if any.

    Returns
    -------
    list[str]
        List of coauthors from the past N years.
    """
    today = datetime.date.today()
    year_cutoff = (today.year - years_back) if years_back else None

    profile = _get_scholar_profile(scholar_id)

    co_authors, affiliations = _get_coauthors_from_pubs(
        profile.get("publications", []), year_cutoff=year_cutoff, my_name=profile.get("name", "")
    )
    
    if filename:
        _dump_to_csv(co_authors, affiliations, filename)
    return co_authors



def _get_scholar_profile(scholar_id: str, sections: list[str] | None = None) -> Author:
    """
    Given a Google Scholar ID, return the full profile.

    Parameters
    ----------
    scholar_id : str
        Google Scholar ID of the author. This is the string of characters
        that appears in the URL of the author's Google Scholar profile
        immediately after "citations?user=" and before "&hl=".
    sections : list[str] | None
        Sections of the profile to return. If None, return the default
        sections selected by scholarly.

    Returns
    -------
    Author
        Full profile of the author.
    """
    if sections is None:
        sections = []
    profile = scholarly.search_author_id(scholar_id)
    return scholarly.fill(profile.__dict__, sections=sections)


def _get_coauthors_from_pubs(
    papers: list[Publication],
    year_cutoff: int | None = None,
    my_name: str | None = None,
) -> Tuple[List[str], List[str]]:
    """
    Get a de-duplicated list of co-authors and affiliations from a list of publications.

    Parameters
    ----------
    papers : list[Publication]
        List of publications.
    year_cutoff : int | None
        Year before which to ignore publications. If set to `None`, all
        publications will be considered.
    my_name : str | None
        Name of the author. If set to `None`, the author will still be
        included in the list of co-authors.

    Returns
    -------
    Tuple(list[str], list[str])
        List of co-authors and affiliations.
    """

    # Filter by year
    current_year = datetime.date.today().year
    if year_cutoff:
        papers_subset = [
            paper
            for paper in papers
            if "bib" in paper and int(paper["bib"].get("pub_year", current_year)) >= year_cutoff
        ]
    else:
        papers_subset = papers

    # Fetch all co-authors from publications
    all_coauthors = []
    for paper in tqdm(papers_subset):
        paper_full = scholarly.fill(paper.__dict__, sections=["authors"])
        coauthors = paper_full["bib"]["author"].split(" and ")

        all_coauthors.extend(coauthors)
        
        #break #test for one publication

    # De-duplicate list of co-authors and remove your own name
    
    all_coauthors = list(set(all_coauthors))
    all_coauthors = _nsf_name_cleanup(all_coauthors)
    # Remove co-authors with repeated last name and first name
    unique_coauthors = []
    seen_names = set()
    for coauthor in all_coauthors:
        last_name, first_name = coauthor.split(", ")
        first_name=first_name.split(" ")[0]
        if (last_name, first_name) not in seen_names:
            seen_names.add((last_name, first_name))
            unique_coauthors.append(coauthor)
        # if coauthor was added previously without middle initial, add middle initial
        elif (last_name, first_name) in seen_names and coauthor.split(", ")[1]!= first_name:
            if last_name+", "+first_name in unique_coauthors:
                unique_coauthors.remove(last_name+", "+first_name)
                unique_coauthors.append(coauthor)

    all_coauthors = unique_coauthors
    if my_name and my_name in all_coauthors:
        all_coauthors.remove(my_name)
        
        

    # Clean up list of co-authors
    
    all_coauthors.sort()
    
    affiliations = []
    for coauthor in all_coauthors:
         # Get the Google Scholar ID and affiliation for each co-author
         # Note: This is a blocking call and may take some time to complete
        affiliation = get_scholar_info(coauthor)
        print( coauthor, affiliation)
        affiliations.append(affiliation)
        
    # Clean up list of affiliations
    affiliations = _nsf_affiliation_cleanup(affiliations)
    

    return all_coauthors, affiliations


def _nsf_name_cleanup(coauthors: list[str]) -> list[str]:
    """
    Clean up names to be in the NSF format of "Lastname, Firstname Middle".

    Parameters
    ----------
    coauthors : list[str]
        List of co-authors.

    Returns
    -------
    list[str]
        List of co-authors with names cleaned up.
    """
    cleaned_coauthors = []
    for coauthor in coauthors:
        name_parts = coauthor.split(" ")
        reordered_name = f"{name_parts[-1]}, {' '.join(name_parts[:-1])}"
        # if there is a middle initial, add it after first name
        if len(name_parts) > 2:
            notlastname= reordered_name.split(", ")[1].split(" ")
            if len(notlastname[0]) <2 : #have to switch first and middle name
                reordered_name = f"{name_parts[-1]}, {notlastname[1]} {notlastname[0]}"
        
        cleaned_coauthors.append(reordered_name)
        
    
    return cleaned_coauthors


def _nsf_affiliation_cleanup(affiliations: list[str]) -> list[str]:
    """
    Clean up affiliations to be in the NSF format department, university, state.

    Parameters
    ----------
    coauthors : list[str]
        List of affiliations.

    Returns
    -------
    list[str]
        List of affiliations cleaned up.
    """

    cleaned_affiliations = []
    for affiliation in affiliations:
        cleaned_affiliation = ""
        if affiliation:
            parts = affiliation.split(", ")
            # if first part of affiliation contains the word "Professor" or "student" or "scientist" remove it
            if any(word in affiliation.lower() for word in ["professor", "student", "scientist", "researcher", "lecturer", "fellow", "scholar"]):
                print(affiliation,"contains title")
                if " at " in affiliation.lower() :
                    print(affiliation, "contains at")
                    #only keep the part after the word "at"
                    cleaned_affiliation = affiliation.split(" at ")[1]
                elif "@" in affiliation.lower():
                    print(affiliation, "contains @")
                    cleaned_affiliation = affiliation.split("@ ")[1]
                else:
                    #remove the part before the word "Professor" or "student" or "scientist"
                    if len(parts)>1:
                        if len(parts)>2:
                            cleaned_affiliation = ", ".join(affiliation.split(", ")[1:])
                        else:
                            cleaned_affiliation = affiliation.split(", ")[1]
                        
            else:
                cleaned_affiliation = affiliation
        else:
            cleaned_affiliation = affiliation

        
        cleaned_affiliations.append(cleaned_affiliation)
    return cleaned_affiliations

def _dump_to_csv(co_authors: list[str],affiliations: list[str],  filename: str | Path = "coauthors.csv") -> None:
    """
    Dump a list of coauthors and affiliations to a CSV file.

    Parameters
    ----------
    co_authors : list[str]
        List of coauthors.
    filename : str | Path
        Name of the CSV file to write to.

    Returns
    -------
    None
    """

    with Path(filename).open(mode="w", encoding="utf-8") as f:
        for i in range(len(co_authors)):
            co_authors[i] = f'"{co_authors[i]}"'
            f.write(f' {co_authors[i]},"{affiliations[i]}" \n')
            
if __name__ == "__main__":
    get_coauthors()
