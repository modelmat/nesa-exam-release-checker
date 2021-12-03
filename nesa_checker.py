from bs4 import BeautifulSoup
import requests
from typing import Dict, List
from datetime import datetime, timedelta
import os
import difflib, sys
import logging
import json


logging.basicConfig(filename="output/backend.log",
#                    encoding='utf-8',
                    level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S %p')

def fetch_directory() -> str:
    req = requests.get("https://educationstandards.nsw.edu.au/wps/portal/nesa/resource-finder/hsc-exam-papers/2021/")
    return req.text


def fetch_subject(url) -> str:
    req = requests.get("https://educationstandards.nsw.edu.au" + url)
    return req.text


def grab_text_body(html: str) -> "bs4.Element.Tag":
    # Parse the page HTML
    soup = BeautifulSoup(html, "lxml")

    for script in soup.find_all("script"): script.extract()
    for style in soup.find_all("style"): style.extract()

    # Fetch the page body from the HTML
    page_body = soup.find("div", attrs={"name": "ibmMainContainer"})
    # Find the relevant text body element in the HTML
    text_body = page_body.find("div", class_ = "stControlBody stOverflowAuto wpthemeControlBody")

    return text_body


def get_url_for_subject(name: str) -> str:
    with open("output/url-mappings.json", "r") as f:
        mappings = json.load(f)
    return mappings[name]


def parse_directory(html: str) -> Dict[str, str]:
    text_body = grab_text_body(html)
    list_el = text_body.find("ul")
    subject_els = list_el.find_all("li")

    subjects = {}
    for subject_el in subject_els:
        if " 2021 HSC exam pack" in subject_el.text:
           subject_name = subject_el.text.replace(" 2021 HSC exam pack", "")
        else:
            subject_name = subject_el.text
            logging.warning(f"{subject_name} does not match expected name structure")

        subject_name = subject_name.replace("/", "").title() # no illegal chars
        subjects[subject_name] = subject_el.a.get("href")

    return subjects


def parse_subject(html: str) -> str:
    text_body = grab_text_body(html)
    text_body = text_body.find("div", class_ = "right-col")

    # Yeet the sharing options
    text_body.find(id="print-share-desktop").extract()
    # Remove duplicate newlines ( do this better )
    output_text = text_body.text.replace("\n\n", "\n")
    return output_text


def format_time(time: datetime) -> str:
    return time.strftime("%Y-%m-%d")


def read_subject_lists(date) -> str:
    with open("output/" + date + "-exam-list.txt", "r") as f:
        return f.read()

def read_subject(subject: str, date) -> str:
    with open("output/" + subject.replace(" ", "-").lower() + "/" + date + ".txt", "r") as f:
        return f.read()


def find_subject_lists() -> List[str]:
    dirlist = os.listdir("output/")
    r = []
    for item in dirlist:
        if "exam-list.txt" in item:
            r.append(item.replace("-exam-list.txt", ""))

    return sorted(r) # oldest to newest

def get_latest_subject_list():
    return find_subject_lists()[-1]


def download():
    logging.info("Downloading Subject List")
    subjects = parse_directory(fetch_directory())
    logging.info("Subject List Downloaded. Processing Updates.")

    with open("output/url-mappings.json", "w") as f:
        json.dump(subjects, f)

    logging.info("Downloading Subjects")
    for (subject_name, url) in subjects.items():
        text = parse_subject(fetch_subject(url))
        path = "output/" + subject_name.replace(" ", "-").lower() + "/"
        if os.path.exists(path):
            indices = get_indices(subject_name)
            with open(path + indices[0] + ".txt", "r") as f: # latest
                prev_text = f.read()

            if prev_text != text:
                logging.info(f"\tWriting updates for {subject_name} to disk")
                with open(path + format_time(datetime.today()) + ".txt", "w") as f:
                    f.write(text)

            else:
                logging.info(f"\tNo new updates for {subject_name}")

        else:
            logging.info(f"\tNew subject {subject_name}. Writing to disk")
            os.mkdir(path)
            with open(path + format_time(datetime.today()) + ".txt", "w") as f:
                f.write(text)    

    output_str = "\n".join(sorted(subjects.keys())) + "\n"
    if find_subject_lists():
        with open("output/{}-exam-list.txt".format(get_latest_subject_list()), "r") as f:
            prev_output_str = f.read()

    else:
            prev_output_str = ""

    if output_str != prev_output_str:
        logging.info("Writing new updates to disk")
        with open("output/{}-exam-list.txt".format(format_time(datetime.today())), "w") as f:
            f.write(output_str)
    else:
        logging.info("No new updates")

    with open("output/last-check.txt", "w") as f:
        f.write(str(datetime.now()))

    logging.info("Downloading Complete")


def get_diff(prev, new, prevtime, newtime):
    return "".join(difflib.unified_diff(
        prev.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=prevtime,
        tofile=newtime,
    ))


def compare_subjects_list(prev_date, new_date):
    new_sbj_list = read_subject_lists(new_date)
    if prev_date is not None:
        prev_sbj_list = read_subject_lists(prev_date)
    else:
        prev_sbj_list = ""
        prev_date = "???"
    
    return get_diff(
        prev_sbj_list,
        new_sbj_list,
        prev_date,
        new_date,
    )


def compare_subject_page(subject, prev_date, new_date):
    new_sbj = read_subject(subject, new_date)

    if prev_date is not None:
        prev_sbj = read_subject(subject, prev_date)
    else:
        prev_sbj = ""
        prev_date = "???"

    return get_diff(
        prev_sbj,
        new_sbj,
        prev_date,
        new_date,
    )



UPDATE_TIME = 15 * 60


def get_time_of_last_check():
    with open("output/last-check.txt", "r") as f:
        return datetime.fromisoformat(f.read())


def time_elapsed() -> int:
    return (datetime.now() - get_time_of_last_check()).total_seconds()


def has_update_time_elapsed():
    return time_elapsed() > UPDATE_TIME


def get_subject_list_updates():
    with open("output/{}-exam-list.txt".format(get_latest_subject_list()), "r") as f:
        subjects = f.read().strip("\n").split("\n")

    out = {}
    for subj in subjects:
        indices = get_indices(subj)
        last_index = max(indices.keys())
        out[subj] = (indices[0], indices[last_index])

    return out

def get_latest_log_output(length=10):
    with open("output/backend.log", "r") as f:
        lines = f.readlines()

    return "".join(lines[-length:])

def get_indices(subject):
    output = {}
    diffs = sorted(os.listdir("output/" + subject.replace(" ", "-").lower()), reverse=True)
    for i, diff_filename in enumerate(diffs):
        output[i] = diff_filename.replace(".txt", "")

    return output

def fetch_diff(subject, index):
    # newest to oldest
    indices = get_indices(subject)

    if index == len(indices)-1:
        # oldest
        # no index of index+1
        return compare_subject_page(subject, None, indices[index])

    else:
        return compare_subject_page(subject, indices[index+1], indices[index])


if __name__ == "__main__":
    download()
    # auto download
