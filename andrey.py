import slackclient
import markovify
import os
import time
import argparse
import re
import sys


STATE_SIZE = 2
USER_ID_REGEX = r"\<\@(.+?)\>"

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

class ArgumentParserError(Exception):
    pass

class ThrowingArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentParserError(message)

def get_markov(user_id):
    try:
        with open(os.path.join(chains_dir, user_id), "r") as infile:
            return markovify.Text.from_json(infile.read())
    except:
        return markovify.Text("", state_size=STATE_SIZE)

def save_markov(user_id, markov):
    with open(os.path.join(chains_dir, user_id), "w") as outfile:
        outfile.write(markov.to_json())


def parse_command(command, message):
    parser = ThrowingArgumentParser()
    subparsers = parser.add_subparsers()
    impersonate_subparser = subparsers.add_parser("impersonate", description="Impersonate the given user")
    impersonate_subparser.set_defaults(function="impersonate")
    impersonate_subparser.add_argument("user", default=None)

    try:
        args, other_args = parser.parse_known_args(command)

        if args.function == "impersonate":
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
        else:
            raise ArgumentParserError("Unkown command")
    except ArgumentParserError as e:
        return "Unknown command"

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument("--key", "-k", default=None, help="Key to use to connect to slack")

    args = parser.parse_args(argv)

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
                        chain = markovify.Text(str(text), state_size=STATE_SIZE)
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

if __name__ == "__main__":
    exit(main())