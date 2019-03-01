import os
import re
import json
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup
from copy import copy, deepcopy
from collections import OrderedDict


class ReportParser:
    """
    - As report of automation test is not friendly to read, this class will filter out class names, case names
      test results, curls, requests and responses from a given report to generate a read-friendly file.
    - And for the purpose of comparing actual response and expected response, they will display on the top of
      each case's test log.
    - ? Define an exception to make error clearly.
    """
    def __init__(self, report, directory, framework_version=3):
        """
        - As test report's format is different between framework 2.X and framework 3.X, it's necessary to give a
          right value to the key framework_version.
        :param report: test report, both file and URL are allowed
        :param directory: directory to store the new generated parse result
        :param framework_version: framework version
        """
        self.file = report
        self.result_dir = directory
        self.version = framework_version

    def parse_report(self):
        """
        - Use the third party package BeautifulSoup4 to transform a complex HTML document into a complex tree of
          Python objects, then pull data out from it, include class name, case number of a class, case name,
          test result of each case and also it's test log.
        - Filter out curls, requests and responses from test log and dump them in to a new file.
        :return: None
        """
        if self.file.startswith('http'):
            html = urllib.request.urlopen(self.file).read()
        else:
            with open(self.file) as f:
                html = f.read()
        soup = BeautifulSoup(html, features='html.parser')
        file_name = self.generate_file_path(soup)

        self.pretty_print('Start to filter out class name and case number in each class.')
        test_summaries = []
        class_tags = soup.find_all('tr', class_=['passClass', 'errorClass', 'failClass', 'bypassClass', 'skipClass'])
        for class_tag in class_tags:
            class_tag_content = [i for i in class_tag.contents if i != '\n']
            class_name = str(class_tag_content[0].string.split('.')[-1:][0])
            class_case_num = str(class_tag_content[1].string)

            class_summary = []
            class_summary.append(class_name)
            class_summary.append(class_case_num)
            test_summaries.append(copy(class_summary))

        self.pretty_print('Start to filter out case name, curls, requests, responses for each case.')
        case_tags = soup.find_all('div', class_='testcase')
        class_results = []
        i = 0
        for test_summary in test_summaries:
            case_results = []
            class_result = {'Class': test_summary[0]}
            case_num = i + int(test_summary[1])

            j = i
            while j < case_num:
                case_name = str(case_tags[j].string).strip()
                case_log = str(case_tags[j].parent.parent.find('pre').string)
                case_result = str(case_tags[j].parent.parent.find('a', class_='popup_link').string.strip('\n').strip())
                if 'skip' in case_result:
                    case_detail = 'Skip case, skip reason is hard to filter out'
                else:
                    if 'download' in case_name:
                        case_detail = 'Download case, still think about how to organize log.'
                    elif 'CLI' in case_name:
                        case_detail = 'CLI case, still think about how to organize log.'
                    else:
                        case_detail = []
                        try:
                            curls = self.generate_curl(case_log)
                            requests = self.generate_case_request(case_log)
                            responses = self.generate_case_response(case_log)
                            actual_and_expect = self.generate_actual_and_expect(case_log)

                            k = 0
                            case_detail.append(actual_and_expect)
                            while k < len(requests):
                                combination = {
                                    'Curl': curls[k],
                                    'Request': requests[k],
                                    'Response': responses[k]
                                }
                                k += 1
                                case_detail.append(copy(combination))
                        except:
                            self.pretty_print('Fault appeared in case: ' + case_name)
                            case_detail.append('Fault appeared !')
                case_content = {'Case': case_name, 'Result': case_result, 'Log': deepcopy(case_detail)}
                case_results.append(deepcopy(case_content))
                j += 1
            i = case_num
            class_result['Results'] = case_results
            class_results.append(copy(class_result))

        self.pretty_print('Start to dump data to file: ' + file_name)
        with open(file_name, 'w') as file:
            json.dump(class_results, file, indent=4)
        self.pretty_print('Parse report over.')

    def generate_curl(self, case_log):
        """
        - Import re module to find curl strings, they always start with 'curl', end with 'yyyy-mm-dd HH:MM:SS'
          or 'yyyy-mm-dd_HH:MM:SS'
        :param case_log: test log of a case
        :return: a list of curls
        """
        curl_pattern = re.compile(' curl .*?\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}| '
                                  'curl .*?\d{4}-\d{2}-\d{2}_\d{2}:\d{2}:\d{2}', re.DOTALL)
        raw_curls = curl_pattern.findall(case_log)
        curls = []
        for raw_curl in raw_curls:
            curl = raw_curl.replace('\n', '')[:-20].strip()
            if '/usr/local/lib' in curl:
                valueless_index = curl.index('/usr/local/lib')
                curl = curl[:valueless_index].strip()
            elif '/usr/lib/' in curl:
                valueless_index = curl.index('/usr/lib')
                curl = curl[:valueless_index].strip()
            curls.append(curl)
        return curls

    def generate_case_request(self, case_log):
        """
        - Import re module to find requests, they always start with 'Start to visit api info',
          end with 'yyyy-mm-dd HH:MM:SS'
        :param case_log: test log of a case
        :return: a list of requests
        """
        request_pattern = re.compile('Start to visit api info.*?\d{4}-\d{2}-\d{2}_\d{2}:\d{2}:\d{2}', re.DOTALL)
        raw_requests = request_pattern.findall(case_log)
        api_requests = []
        for raw_request in raw_requests:
            tmp = raw_request.replace('\n', '').replace(' ', '')[:-19].strip()
            method = self.parse_request_method(tmp.split('URL:')[0])
            url = tmp.split('URL:')[1].split('headers:')[0]
            header = tmp.split('headers:')[1].split('query:')[0]
            body = tmp.split('data:')[1]
            if '/usr/local/lib' in body:
                valueless_index = body.index('/usr/local/lib')
                body = body[:valueless_index].strip()
            elif '/usr/lib/' in body:
                valueless_index = body.index('/usr/lib/')
                body = body[:valueless_index].strip()
            api_request = {
                'Method': method,
                'URL': url,
                'Header': eval(header),
                'Body': json.loads(body) if body != 'None' else None
            }
            api_requests.append(copy(api_request))
        return api_requests

    def generate_case_response(self, case_log):
        """
        - Response body always comes after 'Get response from api:', and its content always in {}, will use a
          balance algorithm to grep it out
        :param case_log: log of test case
        :return: a list of response
        """
        responses = []
        flag = 'Get response from api:'
        raw_responses = self.grep_json_format_data(case_log, flag)
        for raw_response in raw_responses:
            tmp_dict = json.loads(raw_response)
            response = {'statusCode': tmp_dict['statusCode'], 'responseBody': tmp_dict['responseBody']}
            responses.append(deepcopy(response))
        return responses

    def generate_actual_and_expect(self, case_log):
        """
        - Import re module to find actual response and expected response, they always like
          'current result: xxx expected result: xxx statusCode xxx ]'
        - Import OrderedDict to deal OrderedDict data in case log
        :param case_log: log of test case
        :return: a list of actual response and expected response
        """
        # pattern = re.compile('current result:.*?\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', re.DOTALL)
        pattern = re.compile('current result:.*?expected result:.*?statusCode.*?]', re.DOTALL)
        mixed_result = pattern.findall(case_log)[0].replace('\n', '')
        tmp_actual = mixed_result.split('current result:')[1].split('expected result:')[0].strip()[:-1]
        tmp_expect = mixed_result.split('expected result:')[1].strip()
        # tmp_expect = mixed_result.split('expected result:')[1][:-20].strip()
        if 'OrderedDict' in tmp_actual:
            tmp_actual_body = tmp_actual.split('OrderedDict')[1].split("'statusCode'")[0].strip()[:-2]
            actual_status_code = int(tmp_actual.split('statusCode')[1][3:6])
            try:
                actual_response_body = dict(OrderedDict(eval(tmp_actual_body)))
                actual = {'statusCode': actual_status_code, 'responseBody': actual_response_body}
            except:
                self.pretty_print('Unable to parse actual response body with two OrderedDict')
                actual = {'statusCode': actual_status_code, 'responseBody': tmp_actual}
        else:
            actual = eval(tmp_actual)[0]
        if 'OrderedDict' in tmp_expect:
            tmp_expect_body = tmp_expect.split('OrderedDict')[1].split("'statusCode'")[0].strip()[:-2]
            expect_status_code = int(tmp_expect.split('statusCode')[1][3:6])
            try:
                expect_response_body = dict(OrderedDict(eval(tmp_expect_body)))
                expect = {'statusCode': expect_status_code, 'responseBody': expect_response_body}
            except:
                self.pretty_print('Unable to parse expected response body with two OrderedDict')
                expect = {'statusCode': expect_status_code, 'responseBody': tmp_expect}
        else:
            expect = eval(tmp_expect)[0]
        pretty_result = {'Actual result': actual, 'Expected result': expect}
        return pretty_result

    def grep_json_format_data(self, case_log, flag, start_symbol='{', end_symbol='}'):
        """
        - Json data either starts with '{' and ends with '}' or starts with '[' and ends with ']', will use this rule
          to grep json format data out.
        :param case_log: log of test case
        :param flag: a string indicates where is the ideal place to find the first '{' or '['
        :param start_symbol: a symbol like '{', '['
        :param end_symbol: a symbol like '{', '['
        :return: a list of json format data
        """
        flag_index = 0
        raw_responses = []
        increase = len(flag)
        end_position = len(case_log)
        while flag_index < end_position:
            try:
                flag_index = case_log.index(flag, flag_index, end_position)
            except:
                break
            flag_index += increase
            start_index = case_log.index(start_symbol, flag_index, end_position)
            end_index = self.count_end_index(case_log, start_index, start_symbol, end_symbol)
            raw_response = case_log[start_index:end_index]
            if '\n' in raw_response:
                raw_response.replace('\n', '')
            raw_responses.append(raw_response)
        return raw_responses

    def count_end_index(self, case_log, mark, start_symbol, end_symbol):
        """
        - Plus 1 when start_symbol appears and minus 1 when end_symbol appears, when the result is 0, that means we
          got the end index of a json format data.
        :param case_log: test log of case
        :param mark: a index indicates from where to traverse case log
        :param start_symbol: a symbol like '{', '['
        :param end_symbol: a symbol like '}', ']'
        :return: the end index of json data
        """
        k = 0
        while mark < len(case_log):
            if case_log[mark] == start_symbol:
                k += 1
            if case_log[mark] == end_symbol:
                k -= 1
            mark += 1
            if k == 0:
                return mark

    def parse_request_method(self, string):
        """
        Extract request method from string.
        :param string: string always likes 'Executing GET request'
        :return: request method string
        """
        if 'PUT' in string:
            method = 'PUT'
        elif 'POST' in string:
            method = 'POST'
        elif 'DELETE' in string:
            method = 'DELETE'
        else:
            method = 'GET'
        return method

    def generate_file_path(self, soup):
        """
        Capture machine name, number and test start time to generate a new file name in given directory
        :param soup: soup object
        :return: file path string
        """
        is_exist = os.path.exists(self.result_dir)
        if not is_exist:
            os.makedirs(self.result_dir)
            print('Make directory over: {0}.'.format(self.result_dir))
        else:
            print('Directory already exists: {0}.'.format(self.result_dir))

        raw = soup.find('div', class_='heading')
        title = str(raw.find('h1').string)
        tmp_machine = title.split('for')[1].split('[')[0].strip().upper()
        machine = tmp_machine if 'APP' not in tmp_machine else tmp_machine.replace('APP', '')
        raw_start_time = list(raw.find('p').stripped_strings)
        start_time = str(raw_start_time[1]).replace('-', '_').replace(' ', '_').replace(':', '_')
        file_name = machine + '_' + start_time + '.txt'
        file_path = os.path.join(self.result_dir, file_name)
        self.pretty_print('Parse result will be stored in: ' + file_path)
        return file_path

    def pretty_print(self, msg_out):
        current_time = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
        print(current_time + " - " + msg_out)


if __name__ == '__main__':
    html_report = r'C:\Users\Desktop\Report.html'
    result_storage = r'C:\Users\Desktop'
    PR = ReportParser(html_report, result_storage, 3)
    PR.parse_report()
