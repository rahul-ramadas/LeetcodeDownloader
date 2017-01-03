from bs4 import BeautifulSoup
from collections import defaultdict
from multiprocessing.dummy import Pool as ThreadPool
from progressbar import ProgressBar, Percentage, Bar
import argparse
import getpass
import glob
import os
import re
import requests


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


def get_submission_code(submission_id):
    response = leetcode_session.get("https://leetcode.com/submissions/detail/" + submission_id)
    soup = BeautifulSoup(response.text, "html.parser")

    script_with_code = soup.find("script", string=re.compile(r"submissionCode"))

    lang_regex = r"getLangDisplay: '(python|cpp|c|java|csharp)'"
    lang_match = re.search(lang_regex, script_with_code.string)
    lang = lang_match.group(1)

    code_regex = r"submissionCode: '([^']+)'"
    code_match = re.search(code_regex, script_with_code.string)
    code = code_match.group(1)
    code = code.encode("utf-8").decode("unicode-escape")
    code = code.replace("\r\n", "\n")

    return (lang, code)


def get_ac_submissions_on_page(page_no):
    response = leetcode_session.get("https://leetcode.com/submissions/{}/".format(page_no))

    soup = BeautifulSoup(response.text, "html.parser")

    submissions_table = soup.find("table", id="result-testcases")
    if submissions_table is None:
        return {}

    table_body = submissions_table.find("tbody")

    ac_submissions = defaultdict(set)

    for ac_submission in table_body.find_all(
            "a", href=re.compile("/submissions/detail/"), string=re.compile("Accepted")):

        id = ac_submission["href"][len("/submissions/detail/"):-1]

        problem_link = ac_submission.find_previous("a")
        problem_name = problem_link["href"][len("/problems/"):-1]

        ac_submissions[problem_name].add(id)

    return ac_submissions


def get_total_submissions():
    response = leetcode_session.get("https://leetcode.com/progress/")

    soup = BeautifulSoup(response.text, "html.parser")

    script = soup.find("script", string=re.compile(r"total_submissions"))

    regex = r"total_submissions: (\d+)"
    match = re.search(regex, script.string, re.DOTALL)
    total_submissions = match.group(1)

    return int(total_submissions)


def main(path):
    username = input("Username: ")
    password = getpass.getpass()
    print("Logging in to LeetCode...")
    init_leetcode_session(username, password)

    # Get the total number of submissions made
    print("Getting total number of submissions...", end='')
    total_submissions = get_total_submissions()
    print(total_submissions)

    # Figure out how many pages of submissions there are
    SUBMISSIONS_PER_PAGE = 20
    num_pages = (total_submissions + SUBMISSIONS_PER_PAGE - 1) // SUBMISSIONS_PER_PAGE

    # Fetch in parallel all the submissions
    all_ac_submissions = defaultdict(set)
    print("Getting submissions details...")
    pbar = ProgressBar(widgets=[Percentage(), Bar()], maxval=num_pages).start()
    for ac_submissions in pool.imap_unordered(get_ac_submissions_on_page, range(1, num_pages + 1)):
        for prob, subs in ac_submissions.items():
            all_ac_submissions[prob].update(subs)
        pbar.update(pbar.currval + 1)
    pbar.finish()

    # Create all the directories
    if not os.path.exists(path):
        os.makedirs(path)
    for problem in all_ac_submissions:
        prob_dir = os.path.join(path, problem)
        if not os.path.exists(prob_dir):
            os.mkdir(prob_dir)

    total_solved_problems = len(all_ac_submissions)

    # Filter out submissions for which we already have the code
    remove_problems = []
    for prob, subs in all_ac_submissions.items():
        remove_subs = set()
        prob_dir = os.path.join(path, prob)
        for sub in subs:
            fn_pattern = os.path.join(prob_dir, "Solution.{}.*".format(sub))
            fn_matches = glob.glob(fn_pattern)
            if len(fn_matches) > 1:
                raise RuntimeError("More than one file with the same submission ID")

            if len(fn_matches) == 1:
                remove_subs.add(sub)

        subs -= remove_subs
        if not subs:
            remove_problems.append(prob)

    for prob in remove_problems:
        del all_ac_submissions[prob]

    # Fetch the code for new submissions in parallel
    print("Downloading submissions...")

    def fetch_code(problem_id):
        problem, id = problem_id
        lang, code = get_submission_code(id)
        return problem, id, lang, code

    problem_id = [(prob, id) for (prob, subs) in all_ac_submissions.items() for id in subs]

    pbar = ProgressBar(widgets=[Percentage(), Bar()], maxval=max(1, len(problem_id))).start()

    for problem, id, lang, code in pool.imap_unordered(fetch_code, problem_id):
        ext = {"cpp": "cpp", "c": "c", "python": "py","java": "java","csharp": "cs"}[lang]
        filename = "Solution.{}.{}".format(id, ext)
        prob_dir = os.path.join(path, problem)
        with open(os.path.join(prob_dir, filename), "w", encoding="utf-8") as f:
            f.write(code)
        pbar.update(pbar.currval + 1)
    pbar.finish()

    print("Solved: {}".format(total_solved_problems))
    print("New solutions: {}".format(len(problem_id)))
    print("Done.")
    pool.close()
    pool.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download all your LeetCode solutions.")
    parser.add_argument("path", help="Path where solutions should be downloaded")

    args = parser.parse_args()
    main(args.path)
