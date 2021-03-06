import slackclient
import markovify
import os
import time
import argparse
import re
import sys
import json


STATE_SIZE = 2
USER_ID_REGEX = r"\<\@(.+?)\>"

global username

projectname = "andrey3000"

if os.name != "posix":
    import win32com
    from win32com.shell import shellcon, shell
    homedir = shell.SHGetFolderPath(0, shellcon.CSIDL_APPDATA, 0, 0)
else:
    homedir = os.path.join(os.path.expanduser("~"), ".config")
settingsdirectory = os.path.join(homedir, projectname)
if not os.path.isdir(settingsdirectory):
    os.makedirs(settingsdirectory)

chains_dir = os.path.join(settingsdirectory, "chains")
if not os.path.isdir(chains_dir):
    os.makedirs(chains_dir)

texts_dir = os.path.join(settingsdirectory, "texts")
if not os.path.isdir(texts_dir):
    os.makedirs(texts_dir)

class ArgumentParserError(Exception):
    pass

class ThrowingArgumentParser(argparse.ArgumentParser):
    not_error = False
    def error(self, message):
        if not self.not_error:
            raise ArgumentParserError(message)

def get_markov(user_id, path=chains_dir):
    try:
        with open(os.path.join(path, user_id), "r") as infile:
            return AndreyText.from_json(infile.read())
    except:
        return AndreyText("", state_size=STATE_SIZE)

def save_markov(user_id, markov, path=chains_dir):
    with open(os.path.join(path, user_id), "w") as outfile:
        outfile.write(markov.to_json())

class DontErrorAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        parser.not_error = True
        setattr(namespace, self.dest, True)

class AndreyText(markovify.Text):
    def test_sentence_input(self, sentence):
        return True

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False)

def parse_command(command, message):
    parser = ThrowingArgumentParser(add_help=False, prog="@{}".format(username))
    parser.add_argument("--help", "-h", default=False, action=DontErrorAction, nargs=0, help=argparse.SUPPRESS)
    parser.set_defaults(function=None)
    impersonate_parent_parser = argparse.ArgumentParser(add_help=False)
    impersonate_parent_parser.add_argument("user", default=None, help="Highlight of the user you want me to impersonate, or everyone to impersonate a mix of all users.")
    impersonate_parent_parser.add_argument("--help", "-h", default=False, nargs=0, action=DontErrorAction, help=argparse.SUPPRESS)
    impersonate_parent_parser.set_defaults(function="impersonate")

    subparsers = parser.add_subparsers(metavar="{impersonate,write}")
    impersonate_subparser = subparsers.add_parser("impersonate", parents=[impersonate_parent_parser], description="Impersonate the given user", add_help=False, help="Impersonate a user")
    do_subparser = subparsers.add_parser("do", parents=[impersonate_parent_parser], description="Impersonate the given user", add_help=False)
    spoof_subparser = subparsers.add_parser("spoof", parents=[impersonate_parent_parser], description="Impersonate the given user", add_help=False)


    write_subparser = subparsers.add_parser("write", description="Write from a saved text", add_help=False, help="Write in the style of a given text")
    write_subparser.set_defaults(function="write")
    write_subparser.add_argument("name", default=[], nargs="+", help="Name of the text you want me to write like.")
    write_subparser.add_argument("--help", "-h", default=False, action=DontErrorAction, nargs=0, help=argparse.SUPPRESS)

    try:
        args, other_args = parser.parse_known_args(command)

        if args.function is None and args.help:
            return parser.format_help()

        elif args.function == "impersonate":
            if args.help:
                return impersonate_subparser.format_help()
            if args.user is None:
                return "Who should I impersonate?"
            if args.user.lower() == "me":
                uid = message.get("user")
            elif args.user in ("<!everyone>", "everyone"):
                uid = "everyone"
            else:
                m = re.match(USER_ID_REGEX, args.user)
                if not m:
                    return "I don't recognize user {}".format(args.user)
                uid = m.group(1)
            markov = get_markov(uid)
            try:
                sentence = markov.make_sentence()
            except:
                sentence = "Could not impersonate <@{}>, not enough data".format(uid)
            if not sentence:
                sentence = "Could not impersonate <@{}>, not enough data".format(uid)
            return sentence
        elif args.function == "write":
            if args.help:
                return write_subparser.format_help()
            name = "_".join(args.name).lower()
            markov = get_markov(name, path=texts_dir)
            try:
                sentence = markov.make_sentence()
            except:
                sentence = "I do not know how to write {}".format(" ".join(args.name))
            if not sentence:
                sentence = "I do not know how to write {}".format(" ".join(args.name))
            return sentence
        else:
            raise ArgumentParserError("Unkown command")
    except ArgumentParserError as e:
        print e
        return "Unknown command"

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    global username

    parser = argparse.ArgumentParser()
    parser.set_defaults(function=None)
    subparsers = parser.add_subparsers()
    add_text_subparser = subparsers.add_parser("add_text", description="Add a text for andrey to write excerpts for")
    add_text_subparser.set_defaults(function="add_text")

    add_text_subparser.add_argument("text_file", help="File to read text from")
    add_text_subparser.add_argument("name", help="Name to save text as")


    run_subparser = subparsers.add_parser("run", description="Add a text for andrey to write excerpts for")
    run_subparser.set_defaults(function="run")

    run_subparser.add_argument("--key", "-k", default=None, help="Key to use to connect to slack")

    if not argv or argv[0] not in [command for command in subparsers.choices]:
        argv = ["run"] + argv

    args = parser.parse_args(argv)

    if args.function == "run":
        slack_token = None

        try:
            with open(os.path.join(os.path.dirname(__file__), "andrey.key")) as infile:
                slack_token = infile.read().strip()
        except:
            pass

        try:
            slack_token = os.environ["andrey_key"]
        except:
            pass

        if args.key is not None:
            slack_token = args.key

        if not slack_token:
            print "No slack token found!"
            return -1

        client = slackclient.SlackClient(slack_token)

        channels = client.api_call("channels.list")

        if not client.rtm_connect():
            raise Exception("Failed to connect to slack")

        username = client.server.username
        user_id = None
        for uid, user_data in client.server.users.items():
            if user_data.name == username:
                user_id = uid
                break
        assert user_id is not None, "Unable to find own user id"

        while True:
            for slack_message in client.rtm_read():
                if slack_message.get("type") == "message":
                    text = slack_message.get("text")
                    if text is None:
                        continue
                    if not text.startswith("<@{}>".format(user_id)):
                        if slack_message.get("user") == user_id:
                            continue
                        try:
                            chain = AndreyText(str(text), state_size=STATE_SIZE)
                            old_chain = get_markov(slack_message.get("user"))
                            new_chain = markovify.combine([old_chain, chain])
                            save_markov(slack_message.get("user"), new_chain)

                            old_chain = get_markov("everyone")
                            new_chain = markovify.combine([old_chain, chain])
                            save_markov("everyone", new_chain)
                        except Exception as e:
                            print e
                            print text
                    else:
                        message = parse_command(text.split()[1:], slack_message)
                        client.rtm_send_message(slack_message.get("channel"), message)

            time.sleep(.25)

    elif args.function == "add_text":
        with open(args.text_file, "r") as infile:
            data = infile.read()
        m = AndreyText(data)
        name = "_".join(args.name.split(" ")).lower()
        save_markov(name, m, path=texts_dir)


if __name__ == "__main__":
    exit(main())