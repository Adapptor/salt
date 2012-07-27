'''
Module to provide Postgres compatibility to salt.

In order to connect to Postgres, certain configuration is required
in /etc/salt/minion on the relevant minions. Some sample configs
might look like::

    postgres.host: 'localhost'
    postgres.port: '5432'
    postgres.user: 'postgres'
    postgres.pass: ''
    postgres.db: 'postgres'

This data can also be passed into pillar. Options passed into opts will
overwrite options passed into pillar
'''

import logging
from salt.utils import check_or_die
from salt.exceptions import CommandNotFoundError


log = logging.getLogger(__name__)
__opts__ = {}


def __virtual__():
    '''
    Only load this module if the psql bin exists
    '''
    try:
        check_or_die('psql')
        return 'postgres'
    except CommandNotFoundError:
        return False


def version():
    '''
    Return the version of a Postgres server using the output
    from the ``psql --version`` cmd.

    CLI Example::

        salt '*' postgres.version
    '''
    version_line =  __salt__['cmd.run']('psql --version').split("\n")[0]
    name = version_line.split(" ")[1]
    ver = version_line.split(" ")[2]
    return "%s %s" % (name, ver)


def _connection_defaults(user=None, host=None, port=None, sudo_user=None):
    '''
    Returns a tuple of (user, host, port) with config, pillar, or default
    values assigned to missing values.
    '''
    if not user:
        user = __opts__.get('postgres.user') or __pillar__.get('postgres.user') or "postgres"
    if not host:
        host = __opts__.get('postgres.host') or __pillar__.get('postgres.host') or None
    if not port:
        port = __opts__.get('postgres.port') or __pillar__.get('postgres.port') or "5432"
    if not sudo_user:
        sudo_user = __opts__.get('postgres.sudo_user') or __pillar__.get('postgres.sudo_user')

    return (user, host, port, sudo_user)


def _build_command(cmd, user=None, host=None, port=None, sudo_user=None):
    '''
    Return a PostgreSQL command (psql/createdb etc) with the specified parameters.
    '''
    user, host, port, sudo_user = _connection_defaults(user, host, port, sudo_user)
    if user:
        cmd += ' -U %s' % user
    if host:
        cmd += ' -h %s' % host
    if port:
        cmd += ' -p %s' % str(port)
    cmd += ' -w'
    if sudo_user:
        cmd = 'sudo -u %s ' + cmd
    return cmd


'''
Database related actions
'''


def db_list(user=None, host=None, port=None, sudo_user=None):
    '''
    Return a list of databases of a Postgres server using the output
    from the ``psql -l`` query.

    CLI Example::

        salt '*' postgres.db_list
    '''
    cmd = _build_command('psql -l')
    ret = []
    lines = [x for x in __salt__['cmd.run'](cmd).split("\n") if len(x.split("|")) == 6]
    header = [x.strip() for x in lines[0].split("|")]
    for line in lines[1:]:
        line = [x.strip() for x in line.split("|")]
        if not line[0] == "":
            ret.append(list(zip(header[:-1], line[:-1])))

    return ret


def db_exists(name, user=None, host=None, port=None, sudo_user=None):
    '''
    Checks if a database exists on the Postgres server.

    CLI Example::

        salt '*' postgres.db_exists 'dbname'
    '''
    (user, host, port, sudo_user) = _connection_defaults(user, host, port, sudo_user)

    databases = db_list(user=user, host=host, port=port, sudo_user=sudo_user)
    for db in databases:
        if name == dict(db).get('Name'):
            return True

    return False


def db_create(name,
              user=None,
              host=None,
              port=None,
              tablespace=None,
              encoding=None,
              local=None,
              lc_collate=None,
              lc_ctype=None,
              owner=None,
              template=None,
              sudo_user=None):
    '''
    Adds a databases to the Postgres server.

    CLI Example::

        salt '*' postgres.db_create 'dbname'

        salt '*' postgres.db_create 'dbname' template=template_postgis

    '''

    # check if db exists
    if db_exists(name, user, host, port, sudo_user):
        log.info("DB '{0}' already exists".format(name,))
        return False

    cmd_part = ' -h %s' % name

    if tablespace:
        cmd_part = "-D {0} {1}".format(tablespace, cmd_part)

    if encoding:
        cmd_part = "-E {0} {1}".format(encoding, cmd_part)

    if local:
        cmd_part = "-l {0} {1}".format(local, cmd_part)

    if lc_collate:
        cmd_part = "--lc-collate {0} {1}".format(lc_collate, cmd_part)

    if lc_ctype:
        cmd_part = "--lc-ctype {0} {1}".format(lc_ctype, cmd_part)

    if owner:
        cmd_part = "-O {0} {1}".format(owner, cmd_part)

    if template:
        if db_exists(template, user, host, port, sudo_user):
            cmd_part = "-T {template} {cmd}".format(cmd=cmd_part, template=template)
        else:
            log.info("template '{0}' does not exist.".format(template, ))
            return False

    cmd = _build_command('createdb ' + cmd_part, user, host, port, sudo_user)

    __salt__['cmd.run'](cmd)

    if db_exists(name, user, host, port, sudo_user):
        return True
    else:
        log.info("Failed to create DB '{0}'".format(name,))
        return False


def db_remove(name, user=None, host=None, port=None, sudo_user=None):
    '''
    Removes a databases from the Postgres server.

    CLI Example::

        salt '*' postgres.db_remove 'dbname'
    '''
    # check if db exists
    if not db_exists(name, user, host, port, sudo_user):
        log.info("DB '{0}' does not exist".format(name,))
        return False

    # db doesnt exist, proceed
    cmd = _build_command('dropdb {name}'.format(name=name), user, host, port, sudo_user)

    __salt__['cmd.run'](cmd)
    if not db_exists(name, user, host, port):
        return True
    else:
        log.info("Failed to delete DB '{0}'.".format(name, ))
        return False

'''
User related actions
'''


def user_list(user=None, host=None, port=None, sudo_user=None):
    '''
    Return a list of users of a Postgres server.

    CLI Example::

        salt '*' postgres.user_list
    '''
    ret = []
    cmd = _build_command('psql -P pager postgres -c "SELECT * FROM pg_roles"', user, host, port, sudo_user)

    lines = [x for x in __salt__['cmd.run'](cmd).split("\n") if len(x.split("|")) == 13]
    header = [x.strip() for x in lines[0].split("|")]
    for line in lines[1:]:
        line = [x.strip() for x in line.split("|")]
        if not line[0] == "":
            ret.append(list(zip(header[:-1], line[:-1])))

    return ret


def user_exists(name, user=None, host=None, port=None, sudo_user=None):
    '''
    Checks if a user exists on the Postgres server.

    CLI Example::

        salt '*' postgres.user_exists 'username'
    '''
    users = user_list(user=user, host=host, port=port, sudo_user=sudo_user)
    for user in users:
        if name == dict(user).get('rolname'):
            return True

    return False


def user_create(username,
                user=None,
                host=None,
                port=None,
                createdb=False,
                createuser=False,
                encrypted=False,
                password=None,
                sudo_user=None):
    '''
    Creates a Postgres user.

    CLI Examples::

        salt '*' postgres.user_create 'username' user='user' host='hostname' port='port' password='password'
    '''
    # check if user exists
    if user_exists(username, user, host, port, sudo_user):
        log.info("User '{0}' already exists".format(username,))
        return False

    sub_cmd = "CREATE USER {0} WITH".format(username, )
    if password:
        sub_cmd = "{0} PASSWORD '{1}'".format(sub_cmd, password)
    if createdb:
        sub_cmd = "{0} CREATEDB".format(sub_cmd, )
    if createuser:
        sub_cmd = "{0} CREATEUSER".format(sub_cmd, )
    if encrypted:
        sub_cmd = "{0} ENCRYPTED".format(sub_cmd, )

    if sub_cmd.endswith("WITH"):
        sub_cmd = sub_cmd.replace(" WITH", "")

    cmd = _build_command('psql -c "%s"' % sub_cmd, user=user, host=host, port=port, sudo_user=sudo_user)
    return __salt__['cmd.run'](cmd)


def user_update(username,
                user=None,
                host=None,
                port=None,
                createdb=False,
                createuser=False,
                encrypted=False,
                password=None,
                sudo_user=None):
    '''
    Creates a Postgres user.

    CLI Examples::

        salt '*' postgres.user_create 'username' user='user' host='hostname' port='port' password='password'
    '''
    (user, host, port, sudo_user) = _connection_defaults(user, host, port, sudo_user)

    # check if user exists
    if not user_exists(username, user, host, port, sudo_user):
        log.info("User '{0}' does not exist".format(username,))
        return False

    sub_cmd = "ALTER USER {0} WITH".format(username, )
    if password:
        sub_cmd = "{0} PASSWORD '{1}'".format(sub_cmd, password)
    if createdb:
        sub_cmd = "{0} CREATEDB".format(sub_cmd, )
    if createuser:
        sub_cmd = "{0} CREATEUSER".format(sub_cmd, )
    if encrypted:
        sub_cmd = "{0} ENCRYPTED".format(sub_cmd, )

    if sub_cmd.endswith("WITH"):
        sub_cmd = sub_cmd.replace(" WITH", "")

    cmd = _build_command('psql -c "%s"' % sub_cmd, user, host, port, sudo_user)
    return __salt__['cmd.run'](cmd)


def user_remove(username, user=None, host=None, port=None, sudo_user=None):
    '''
    Removes a user from the Postgres server.

    CLI Example::

        salt '*' postgres.user_remove 'username'
    '''
    # check if user exists
    if not user_exists(username, user, host, port, sudo_user):
        log.info("User '{0}' does not exist".format(username,))
        return False

    # user exists, proceed
    cmd = _build_command('dropuser %s' % username)
    __salt__['cmd.run'](cmd)
    if not user_exists(username, user, host, port):
        return True
    else:
        log.info("Failed to delete user '{0}'.".format(username, ))
        return False
