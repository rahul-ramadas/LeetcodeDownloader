from bs4 import BeautifulSoup
import requests
import re
from multiprocessing.dummy import Pool as ThreadPool
import os
import getpass
from progressbar import ProgressBar, Percentage, Bar
import argparse
import functools
import glob


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
        return (0, 0)

    prob_dir = os.path.join(path, problem_name)
    if not os.path.exists(prob_dir):
        os.mkdir(prob_dir)

    ac_submissions = len(submission_ids)
    new_submissions = 0

    for id in submission_ids:
        fn_pattern = os.path.join(prob_dir, "Solution.{}.*".format(id))
        fn_matches = glob.glob(fn_pattern)
        if len(fn_matches) > 1:
            raise RuntimeError("More than one file with the same submission ID")

        if len(fn_matches) == 1:
            continue

        new_submissions += 1

        lang, code = get_submission_code(id)
        ext = {"cpp": "cpp", "c": "c", "python": "py"}[lang]
        filename = "Solution.{}.{}".format(id, ext)
        with open(os.path.join(prob_dir, filename), "w") as f:
            f.write(code)

    return (ac_submissions, new_submissions)


def main(path):
    username = input("Username: ")
    password = getpass.getpass()
    init_leetcode_session(username, password)
    problems = get_unlocked_problem_names()
    pbar = ProgressBar(widgets=[Percentage(), Bar()], maxval=len(problems)).start()

    if not os.path.exists(path):
        os.makedirs(path)

    total_ac_count = 0
    total_new_count = 0
    solved_count = 0

    for ac_count, new_count in pool.imap_unordered(functools.partial(process_problem, path), problems):
        solved_count += 1 if ac_count else 0
        total_ac_count += ac_count
        total_new_count += new_count
        pbar.update(pbar.currval + 1)
    pbar.finish()

    print("Solved: {}".format(solved_count))
    print("Total AC submissions: {}".format(total_ac_count))
    print("New solutions: {}".format(total_new_count))
    pool.close()
    pool.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download all your LeetCode solutions.")
    parser.add_argument("path", help="Path where solutions should be downloaded")

    args = parser.parse_args()
    main(args.path)
