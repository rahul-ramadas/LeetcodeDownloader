from bs4 import BeautifulSoup
import requests
import re
from multiprocessing.dummy import Pool as ThreadPool
import os
import getpass
from progressbar import ProgressBar, Percentage, Bar
import argparse
import functools


leetcode_session = None
pool = ThreadPool(32)


def init_leetcode_session(username, password):
    url = 'https://leetcode.com/accounts/login/'

    session = requests.Session()
    session.get(url)
    csrftoken = session.cookies['csrftoken']

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": url
    }

    payload = {
        "csrfmiddlewaretoken": csrftoken,
        "login": username,
        "password": password
    }

    session.post(url, data=payload, headers=headers)

    global leetcode_session
    leetcode_session = session


def get_unlocked_problem_names():
    response = leetcode_session.get("https://leetcode.com/problemset/algorithms/")
    soup = BeautifulSoup(response.text, "html.parser")

    problems_list = []

    problems_div = soup.find("div", id="problemListRow")
    problems_table = problems_div.find("tbody")

    for problem_link in problems_table("a"):
        lock_icon = problem_link.find_next_sibling("i", class_="fa fa-lock")
        if lock_icon is not None:
            continue

        problem_name = problem_link["href"][len("/problems/"):-1]
        problems_list.append(problem_name)

    return problems_list


def get_accepted_submissions(problem_name):
    response = leetcode_session.get(
            "https://leetcode.com/problems/{}/submissions/".format(problem_name))

    soup = BeautifulSoup(response.text, "html.parser")

    submissions_table = soup.find("table", id="result_testcases")
    if submissions_table is None:
        return []

    table_body = submissions_table.find("tbody")

    submission_ids = []

    for ac_submission in table_body.find_all(
            "a", href=re.compile("/submissions/detail/"), string=re.compile("Accepted")):
        id = ac_submission["href"][len("/submissions/detail/"):-1]
        submission_ids.append(id)

    return submission_ids


def get_submission_code(submission_id):
    response = leetcode_session.get("https://leetcode.com/submissions/detail/" + submission_id)
    soup = BeautifulSoup(response.text, "html.parser")

    script_with_code = soup.find("script", string=re.compile(r"scope\.code\."))

    regex = r"scope\.code\.(python|cpp|c) = '(.+)'"
    match = re.search(regex, script_with_code.string)
    lang = match.group(1)
    code = match.group(2)
    code = code.encode("utf-8").decode("unicode-escape")
    code = code.replace("\r\n", "\n")

    return (lang, code)


def process_problem(path, problem_name):
    submission_ids = get_accepted_submissions(problem_name)
    if not submission_ids:
        return False

    prob_dir = os.path.join(path, problem_name)
    if not os.path.exists(prob_dir):
        os.mkdir(prob_dir)

    for id in submission_ids:
        lang, code = get_submission_code(id)
        ext = {"cpp": "cpp", "c": "c", "python": "py"}[lang]
        filename = "Solution.{}.{}".format(id, ext)
        with open(os.path.join(prob_dir, filename), "w") as f:
            f.write(code)

    return True


def main(path):
    username = input("Username: ")
    password = getpass.getpass()
    init_leetcode_session(username, password)
    problems = get_unlocked_problem_names()
    pbar = ProgressBar(widgets=[Percentage(), Bar()], maxval=len(problems)).start()
    solved_count = 0

    if not os.path.exists(path):
        os.makedirs(path)

    for solved in pool.imap_unordered(functools.partial(process_problem, path), problems):
        solved_count += solved
        pbar.update(pbar.currval + 1)
    pbar.finish()

    print("Solved: {}".format(solved_count))
    pool.close()
    pool.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download all your LeetCode solutions.")
    parser.add_argument("path", help="Path where solutions should be downloaded")

    args = parser.parse_args()
    main(args.path)
