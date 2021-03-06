import re
import json
import requests
import urllib
from bs4 import BeautifulSoup

from datetime import datetime
from inspect import getdoc, getargspec

from gnotty.bots import events
from gnotty.conf import settings


class CommandMixin(object):
    """
    Mixin for bots that provides a handful of basic commands.
    """

    def __init__(self, *args, **kwargs):
        self.joined = {}
        self.quit = {}
        super(CommandMixin, self).__init__(*args, **kwargs)

    @events.on("namreply")
    def handle_joined(self, connection, event):
        """
        Store join times for current nicknames when we first join.
        """
        nicknames = [s.lstrip("@+") for s in event.arguments()[-1].split()]
        for nickname in nicknames:
            self.joined[nickname] = datetime.now()

    @events.on("pubmsg")
    def respond(self, connection, event):
        author = event.source().split('!')[0].strip()
        for message in event.arguments():
            reply = self.handle_issue(message)
            if isinstance(reply, list):
                for msg in reply:
                    self.message_channel("%s: %s" % (author, msg))
            self.handle_PR(message)

    def handle_issue(self, msg):
        issues = re.findall("#[0-9]+", msg)
        if len(issues) == 0:
            return None
        url = \
            "https://api.bitbucket.org/1.0/repositories/yt_analysis/yt/issues"
        reply = []
        for issue in issues:
            ino = int(issue[1:])
            r = requests.get('%s/%i' % (url, ino))
            if r.status_code != 200:
                continue
            payload = json.loads(r.text)
            link = "https://bitbucket.org/yt_analysis/yt/issue/%i" % ino
            title = payload['title']
            status = payload['status']
            try:
                rep = payload['reported_by']
            except KeyError:
                rep = {'first_name': "John", 'last_name': "Doe"}
            reporter = "%s %s" % (rep['first_name'], rep['last_name'])
            try:
                asg = payload['responsible']
            except KeyError:
                asg = {'first_name': "unassigned", 'last_name': ""}
            assignee = "%s %s" % (asg['first_name'], asg['last_name'])
            reply.append("%s \"%s\"; %s; %s -> %s" % (link, title, status,
                                                      reporter, assignee))
        if len(reply) > 0:
            return reply
        else:
            return None

    def handle_PR(self, msg):
        prs = re.findall("PR[0-9]+", msg)
        if len(prs) == 0:
            return None
        reply = ""
        for pr in prs:
            url = 'https://bitbucket.org/yt_analysis/yt/pull-request/'+pr[2:]
            print url
            html_file = urllib.urlretrieve(url)
            f = open(html_file[0], 'r')
            html_doc = "".join([line.strip() for line in f.readlines()])
            f.close()
            soup = BeautifulSoup(html_doc)

            title_raw = soup.title.string
            r_pr = re.compile('''Pull request #(.*) Bitbucket''')
            try:
                title = re.search(r_pr, title_raw).group(1)[:-1]
            except:
                print "something went wrong"
                return

            author = soup.find_all('div', attrs={'class': 'summary'})[0].a.contents[0]

            msg = "PR %s by %s - %s" % (title, author, url)
            self.message_channel(msg)


    @events.on("join")
    def handle_join(self, connection, event):
        """
        Store join time for a nickname when it joins.
        """
        nickname = self.get_nickname(event)
        self.joined[nickname] = datetime.now()

    @events.on("quit")
    def handle_quit(self, connection, event):
        """
        Store quit time for a nickname when it quits.
        """
        nickname = self.get_nickname(event)
        self.quit[nickname] = datetime.now()
        del self.joined[nickname]

    def timesince(self, when):
        """
        Returns human friendly version of the timespan between now
        and the given datetime.
        """
        units = (
            ("year",   60 * 60 * 24 * 365),
            ("week",   60 * 60 * 24 * 7),
            ("day",    60 * 60 * 24),
            ("hour",   60 * 60),
            ("minute", 60),
            ("second", 1),
        )
        delta = datetime.now() - when
        total_seconds = delta.days * 60 * 60 * 24 + delta.seconds
        parts = []
        for name, seconds in units:
            value = total_seconds / seconds
            if value > 0:
                total_seconds %= seconds
                s = "s" if value != 1 else ""
                parts.append("%s %s%s" % (value, name, s))
        return " and ".join(", ".join(parts).rsplit(", ", 1))

    def commands_dict(self):
        return dict([(c.event["args"][0], c) for c in self.events["command"]])

    ##############
    #  Commands  #
    ##############

    @events.on("command", "!version")
    def version(self, event):
        """
        Shows version information.
        """
        name = "%s.%s" % (self.__class__.__module__, self.__class__.__name__)
        return "%s [%s]" % (settings.GNOTTY_VERSION_STRING, name)

    @events.on("command", "!commands")
    def commands(self, event):
        """
        Lists all available commands.
        """
        commands = sorted(self.commands_dict().keys())
        return "Available commands: %s" % " ".join(commands)

    @events.on("command", "!help")
    def help(self, event, command_name=None):
        """
        Shows the help message for the bot. Takes an optional command name
        which when given, will show help for that command.
        """
        if command_name is None:
            return ("Type !commands for a list of all commands. Type "
                    "!help [command] to see help for a specific command.")
        try:
            command = self.commands_dict()[command_name]
        except KeyError:
            return "%s is not a command" % command_name

        argspec = getargspec(command)
        args = argspec.args[2:]
        defaults = argspec.defaults or []
        for i in range(-1, -len(defaults) - 1, -1):
            args[i] = "%s [default: %s]" % (args[i], defaults[i])
        args = ", ".join(args)
        help = getdoc(command).replace("\n", " ")
        return "help for %s: (args: %s) %s" % (command_name, args, help)

    @events.on("command", "!uptime")
    def uptime(self, event, nickname=None):
        """
        Shows the amount of time since the given nickname has been
        in the channel. If no nickname is given, I'll use my own.
        """
        if nickname and nickname != self.nickname:
            try:
                uptime = self.timesince(self.joined[nickname])
            except KeyError:
                return "%s is not in the channel" % nickname
            else:
                if nickname == self.get_nickname(event):
                    prefix = "you have"
                else:
                    prefix = "%s has" % nickname
                return "%s been here for %s" % (prefix, uptime)
        uptime = self.timesince(self.joined[self.nickname])
        return "I've been here for %s" % uptime

    @events.on("command", "!seen")
    def seen(self, event, nickname):
        """
        Shows the amount of time since the given nickname was last
        seen in the channel.
        """
        try:
            self.joined[nickname]
        except KeyError:
            pass
        else:
            if nickname == self.get_nickname(event):
                prefix = "you are"
            else:
                prefix = "%s is" % nickname
            return "%s here right now" % prefix
        try:
            seen = self.timesince(self.quit[nickname])
        except KeyError:
            return "%s has never been seen" % nickname
        else:
            return "%s was last seen %s ago" % (nickname,  seen)

    @events.on("command", "!users")
    def users(self, event):
        """
        Shows the list of users currently in the channel.
        """
        return "Current users: %s" % ", ".join(sorted(self.joined.keys()))
