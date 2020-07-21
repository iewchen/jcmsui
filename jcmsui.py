#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import subprocess
import time
from base64 import b64encode
from hashlib import sha256
from json import dumps,loads
import toml

from contextlib import closing
from flask import Flask, request, redirect, url_for, send_file, \
     render_template, make_response, flash, g, send_from_directory
from flask import jsonify,Response
from wtforms import Form, BooleanField, TextField, PasswordField, validators
from flask_login import LoginManager
from flask_login import UserMixin, current_user
from flask_login import login_user, logout_user, login_required
from flaskext.mysql import MySQL

import jinja2
import subprocess
from jinja2 import Template

import redis

latex_jinja_env = jinja2.Environment(
	block_start_string = '\BLOCK{',
	block_end_string = '}',
	variable_start_string = '\VAR{',
	variable_end_string = '}',
	comment_start_string = '\#{',
	comment_end_string = '}',
	line_statement_prefix = '%%',
	line_comment_prefix = '%#',
	trim_blocks = True,
	autoescape = False,
	loader = jinja2.FileSystemLoader(os.path.abspath('./templates'))
)


APPDIR = os.path.abspath(os.path.dirname(__file__))
CFG_FILE = os.path.join(APPDIR, 'config.toml')
APP_TMP = os.path.join(APPDIR, 'tmp')

cfg = toml.load(CFG_FILE)

app = Flask(__name__)
app.secret_key = cfg['flask_secret_key']
app.debug = cfg['debug']
app.config.from_object(__name__)
app.config.from_envvar('FLASKR_SETTINGS', silent=True)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True


mysql = MySQL()
# MySQL configurations
app.config['MYSQL_DATABASE_USER'] = cfg['db_user']
app.config['MYSQL_DATABASE_PASSWORD'] = cfg['db_pass']
app.config['MYSQL_DATABASE_DB'] = cfg['db_name']
app.config['MYSQL_DATABASE_HOST'] = cfg['db_host']
mysql.init_app(app)
# max payload 32MB
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # default login view for login_manager
login_manager.login_message = 'Please log in'

#RE_CAGENAME = re.compile('([a-zA-Z0-9]+)-(\d+)([a-zA-Z]?)-(.+)')
RE_CAGENAME = re.compile('(.*?)-(\d+)([a-zA-Z]?)-(.+)')

cache = redis.Redis(host=cfg['redis_host'],decode_responses=True,
        port=cfg['redis_port'], db=0)
CACHE_LIFE = 5  # 5 sec


def cache_set(k, v, life=CACHE_LIFE):
    print('cache set %s' % k)
    g.r.set(k, v)
    g.r.expire(k, life)

def cache_get(k):
    q = g.r.get(k)
    if q:
        print('cache hit for %s' % k)
    return q

def cache_del(k):
    return g.r.delete(k)



# http://flask.pocoo.org/snippets/35/
class ReverseProxied(object):
    '''Wrap the application in this middleware and configure the
    front-end server to add these headers, to let you quietly bind
    this to a URL other than / and to an HTTP scheme that is
    different than what is used locally.

    In nginx:
    location /myprefix {
        proxy_pass http://192.168.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Scheme $scheme;
        proxy_set_header X-Script-Name /myprefix;
        }

    :param app: the WSGI application
    '''
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name
            path_info = environ['PATH_INFO']
            if path_info.startswith(script_name):
                environ['PATH_INFO'] = path_info[len(script_name):]

        scheme = environ.get('HTTP_X_SCHEME', '')
        if scheme:
            environ['wsgi.url_scheme'] = scheme
        return self.app(environ, start_response)

app.wsgi_app = ReverseProxied(app.wsgi_app)


# -------------------------- User & Auth ---------------------
class User(UserMixin):
    def __init__(self, username):
        if username:
            self.username = username
        else:
            self.username = None

    def get_id(self):
        ''' this method will be called by load_user '''
        print(type(self.username))
        return self.username
        #return unicode(self.username)

    def __repr__(self):
        return '<User %r>' % (self.username)


@login_manager.user_loader
def load_user(username):
    user = User(username)
    if user.username:
        return user
    else:
        return None


class LoginForm(Form):
    username = TextField('username', [validators.Required()])
    password = PasswordField('password', [validators.Required()])
    remember_me = BooleanField('remember_me', default=False)


def sanit_name(nstr):
    nstr = nstr.strip()
    return ' '.join(nstr.split())


def encode_passwd(cleartxt):
    # password hash algorithm from JCMSWeb
    return b64encode(sha256(cleartxt.encode('utf-8')).digest()).decode('utf-8')


def user_lookup(username):
    # lookup user password, first and last name from mysql db
    # Return:   FirstName, LastName, HashedPassword(or None)
    sql = 'SELECT FirstName,LastName,Password_ from User WHERE UserName=%s'
    row = query_db(sql, (username,), one=True)
    if row:
        return row
    else:
        return (None, None, None)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user and g.user.is_authenticated:
        return redirect(url_for('show_index'))

    form = LoginForm(request.form)
    if request.method == 'POST' and form.validate():
        s_name = sanit_name(form.username.data)
        passwd = form.password.data
        remember_me = form.remember_me.data

        # first and last name is unused for now
        firstname,lastname,hashp = user_lookup(s_name)
        if hashp and hashp == encode_passwd(passwd):
            user = User(s_name)
            login_user(user, remember=remember_me)

            return redirect(url_for('show_index'))

        else:
            flash('Either the username or the password is wrong, please try '
                  'again.')
            return redirect(url_for('login', _external=False))

    return render_template('login.html', form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('show_index'))

# -------------------------- End User & Auth ---------------------

# -------------------------- Helpler func ---------------------
@app.before_request
def before_request():
    g.db = mysql.get_db().cursor()
    g.user = current_user
    g.r = cache


@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    ''' wrap the db query, fetch into one step '''
    g.db.execute(query, args)
    rv = g.db.fetchall()
    #cur.close()
    return (rv[0] if rv else None) if one else rv

# -------------------------- End Helpler func ---------------------

@app.route('/static/<path:path>')
def send_static(fname):
    return send_from_directory(path)


@app.route('/')
@app.route('/index.html')
@login_required
def show_index():
    user = g.user
    return render_template('index.html', user=user)



def extract_rack_location(cagename_in_db):
    # cagename must indicate the location, e.g. Rackxx-7B-yyy form
    m = RE_CAGENAME.match(cagename_in_db)
    if m:
        rack_name = m.group(1)
        rack_rowid = m.group(2)
        rack_colid = m.group(3)
        cagedesc = m.group(4)
    else:
        rack_name = 'N/A'
        rack_rowid = 99  # non-exist row
        rack_colid = ''
        cagedesc = 'N/A'

    return (rack_name, rack_rowid, rack_colid, cagedesc)



SQL_ALLMICE = """
SELECT MouseID,Sex,Strain,AgeInDays,Color,BreedingStatus,
       PenID,PenName,labSymbol,Genotype,DOB,MouseKey,MComment
FROM
(SELECT
    Mouse.ID as MouseID , Mouse.sex as Sex, Mouse._mouse_key as MouseKey,
    TIMESTAMPDIFF(DAY,Mouse.birthDate,CURDATE()) as AgeInDays,
    Mouse.birthDate as DOB,Mouse.comment as MComment,
    Mouse.breedingStatus as BreedingStatus , Strain.strainName as Strain ,
    Container.containerID as PenID , Container.containerName as PenName ,
    Mouse.coatColor as Color,
    Genotype._gene_key,
    CONCAT(Genotype.allele1, "/",Genotype.allele2) as Genotype
FROM Mouse
Left Join Strain On Strain.`_strain_key` = Mouse.`_strain_key`
Left Join Container On Container.`_container_key` = Mouse.`_pen_key`
Left Join Genotype on Genotype.`_mouse_key` = Mouse.`_mouse_key`
WHERE Mouse.lifeStatus = 'A') m
LEFT JOIN Gene on Gene.`_gene_key` = m.`_gene_key`
"""


@app.route('/api/allmice.json')
@login_required
def get_allmice():
    js = cache_get('api_allmice.json')
    if js:
        return Response(js, status=200, mimetype='application/json')

    rows = query_db(SQL_ALLMICE)
    res = {'racks': {}, 'cages': {}, 'mice': {}}
    cages = {}
    mice = {}
    for r in rows:
        mk = r[11]
        genotype = '%s %s' % (r[8], r[9])

        # mouse may have multiple genotype
        if mk in mice:
            mice[mk]['genotype'].append(genotype)
            continue

        mouse = {
                'tag': r[0],
                'sex': r[1],
                'strain': r[2],
                'age': r[3],
                'color': r[4],
                'breedingstatus': r[5],
                'cageid': r[6],
                'cagename': r[7] if r[7] else '99-None',
                'genotype': [],
                'dob': r[10],
                'mk': r[11],
                'comment': r[12],
                'ismating': 0,
                }

        mouse['dob'] = mouse['dob'].strftime('%Y-%m-%d')
        mouse['genotype'].append(genotype)

        mice[mk] = mouse

        rack_name, rack_rowid, rack_colid, cagedesc = extract_rack_location(
                                                            mouse['cagename'])
        if mouse['cageid'] not in cages:
            cages[mouse['cageid']] = {'id': mouse['cageid'],
                                      'name': mouse['cagename'],
                                      'rack': rack_name,
                                      'row': rack_rowid,
                                      'col': rack_colid,  # for sort
                                      'desc': cagedesc,
                                      'micelist': []}

        cages[mouse['cageid']]['micelist'].append(mouse)

    # keep only mouse_key in cage for efficiency
    tmp = {}
    for k,v in cages.items():
        micelist = v['micelist']
        micelist.sort(key=lambda m: m['genotype'])
        micelist.sort(key=lambda m: m['sex'])
        tmp = [m['mk'] for m in micelist]
        v['micelist'] = tmp

    res['cages'] = cages

    racks = {}
    for cid,cage in cages.items():
        if cage['rack'] not in racks:
            racks[cage['rack']] = {}

        rack = racks[cage['rack']]
        # store cages in row
        r = cage['row']
        if r not in rack:
            rack[r] = []
        rack[r].append(cage)

    for rackname, rack in racks.items():
        # keep only cage_id in rack
        for r,r_cages in rack.items():
            r_cages.sort(key=lambda c: c['col'])
            cage_ids = [c['id'] for c in r_cages]
            rack[r] = cage_ids
            #res['rack'][r] = [c['id'] for c in cages]

    res['racks'] = racks
    res['mice'] = mice
    mark_mating(res)  # find mating in the same cage

    js = dumps(res)
    cache_set('api_allmice.json', js)

    return Response(js, status=200, mimetype='application/json')


def find_mating_dam(sire_mk):
    sql = ('SELECT _dam1_key,_dam2_key from Mating WHERE _sire_key=%s '
           'AND retiredDate IS NULL ORDER BY matingDate DESC LIMIT 1')
    row = query_db(sql, (sire_mk), one=True)
    dam1 = dam2 = -1
    if row:
        dam1, dam2 = row

    return (dam1, dam2)


def mark_mating(allmice):
    ''' looking for mating dam of breeding male, modify allmice in-situ '''
    cages = allmice['cages']
    for k, cage in cages.items():
        micelist = cage['micelist']
        for mk in micelist:
            mouse = allmice['mice'][mk]
            if mouse['sex'] == 'M' and mouse['breedingstatus'] == 'B':
                dam1, dam2 = find_mating_dam(mk)
                if dam1 in micelist:
                    allmice['mice'][dam1]['ismating'] = 1
                    allmice['mice'][mk]['ismating'] = 1

                if dam2 in micelist:
                    allmice['mice'][dam2]['ismating'] = 1
                    allmice['mice'][mk]['ismating'] = 1



SQL_MANYMICE = """
SELECT MouseID,Sex,Strain,AgeInDays,Color,BreedingStatus,
       PenID,PenName,labSymbol,Genotype,DOB,MouseKey,origin,generation,
       _litter_key,litterID,MouseComment,lifeStatus
FROM
(SELECT
    Mouse.ID as MouseID , Mouse.sex as Sex, Mouse._mouse_key as MouseKey,
    TIMESTAMPDIFF(Day,Mouse.birthDate,CURDATE()) as AgeInDays,
    Mouse.birthDate as DOB, Mouse.origin,Mouse.generation,
    Mouse.breedingStatus as BreedingStatus , Strain.strainName as Strain ,
    Container.containerID as PenID , Container.containerName as PenName ,
    Mouse.coatColor as Color,Mouse._litter_key,Mouse.comment as MouseComment,
    Mouse.lifeStatus as lifeStatus,
    Genotype._gene_key,
    lt.litterID,
    CONCAT(Genotype.allele1, "/",Genotype.allele2) as Genotype
FROM Mouse
Left Join Strain On Strain.`_strain_key` = Mouse.`_strain_key`
Left Join Container On Container.`_container_key` = Mouse.`_pen_key`
Left Join Genotype on Genotype.`_mouse_key` = Mouse.`_mouse_key`
Left Join Litter lt on Mouse._litter_key = lt._litter_key
WHERE Mouse._mouse_key IN (%s) ) m
LEFT JOIN Gene on Gene.`_gene_key` = m.`_gene_key`
"""
def get_manymice(mice_keys):
    """ mice_keys is a list """

    ls_str = cache_get('lifestatus')
    if not ls_str:
        lfs = query_db('SELECT lifeStatus,description FROM LifeStatus')
        res_ls = {}
        for r in lfs:
            res_ls[r[0]] = r[1]
        ls_str = dumps(res_ls)
        cache_set('lifestatus', ls_str, 3600)
    lifestatus = loads(ls_str)

    fmt_str = ','.join(['%s'] * len(mice_keys))
    rows = query_db(SQL_MANYMICE % fmt_str, tuple(mice_keys))
    mice = {}
    for r in rows:
        mouse_key = r[11]
        genotype = '%s %s' % (r[8], r[9])

        # mouse may have multiple genotype
        if mouse_key in mice:
            mice[mouse_key]['genotype'].append(genotype)
            continue

        mouse = {
                'tag': r[0],
                'sex': r[1],
                'strain': r[2],
                'age': r[3],
                'color': r[4],
                'breedingstatus': r[5],
                'cageid': r[6],
                'cagename': r[7],
                'genotype': [],
                'dob': r[10],
                'mk': r[11],
                'origin': r[12],
                'generation': r[13],
                'litterkey': r[14],
                'litterid': r[15],
                'comment': r[16],
                'lifestatus': lifestatus[r[17]],
                }

        mouse['dob'] = mouse['dob'].strftime('%Y-%m-%d')
        mouse['genotype'].append(genotype)

        mice[mouse_key] = mouse

    return mice


@app.route('/api/mouse.json')
@login_required
def get_mouse():
    '''
    return mouse detail including mating history
    '''
    mk = request.args.get('mk')

    js = cache_get('api_mouse.json_%s' % mk)
    if js:
        return Response(js, status=200, mimetype='application/json')


    row = query_db('select sex from Mouse where _mouse_key=%s', (mk,), True)
    sex = row[0]
    if sex == 'M':
        sql = '''
SELECT m1key,m2key,matingDate,retiredDate,matingID,
       lt._litter_key,lt.litterID,lt.totalBorn,lt.birthDate,lt.comment
FROM
(select _dam1_key as m1key,_dam2_key as m2key,matingDate,retiredDate,
 matingID,_mating_key from Mating
 where _sire_key=%s order by matingDate ASC) mt
LEFT JOIN Litter lt ON lt._mating_key=mt._mating_key
        '''

        rows = query_db(sql, (mk,))
    else:
        sql = '''
SELECT m1key,m2key,matingDate,retiredDate,matingID,
       lt._litter_key,lt.litterID,lt.totalBorn,lt.birthDate,lt.comment
FROM
(select _sire_key as m1key,"-1" as m2key,matingDate,retiredDate,
 matingID, _mating_key from Mating
 where (_dam1_key=%s or _dam2_key=%s) order by matingDate ASC) mt
LEFT JOIN Litter lt ON lt._mating_key=mt._mating_key
        '''

        rows = query_db(sql, (mk,mk))

    mating_mice = {mk: None}
    mating = {}
    for r in rows:
        mtid = r[4]
        if mtid in mating:
            mat = mating[mtid]
        else:
            mat = { 'm1': r[0],
                    'm2': r[1],
                    'matingdate': r[2],
                    'retiredate': r[3],
                    'matingid': r[4],
                    'litters': [],
                    }

            mat['matingdate'] = mat['matingdate'].strftime('%Y-%m-%d')
            if mat['retiredate']:
                mat['retiredate'] = mat['retiredate'].strftime('%Y-%m-%d')

            mating[mtid] = mat

        litter = {'litterkey': r[5], 'litterid': r[6], 'litterborn': r[7],
                  'litterdob': r[8], 'littercomment': r[9]}

        if litter['litterdob']:
            litter['litterdob'] = litter['litterdob'].strftime('%Y-%m-%d')

        if litter['litterid']:
            mat['litters'].append(litter)

        mating_mice[mat['m1']] = 1
        mating_mice[mat['m2']] = 1

    mice_keys = [m for m in mating_mice]
    mice = get_manymice(mice_keys)

    matinglist = [mating[x] for x in mating]
    matinglist.sort(key=lambda m: m['matingdate'])

    js = dumps({'mice': mice, 'mating': matinglist})
    cache_set('api_mouse.json_%s' % mk, js)
    return Response(js, status=200, mimetype='application/json')


SQL_MOUSE_LITTER = """
SELECT lt.comment,mt._sire_key,_dam1_key,_dam2_key,
       lt.birthDate,lt.weanDate,lt.totalBorn,lt.litterID
FROM Litter lt
Left Join Mating mt on lt.`_mating_key` = mt.`_mating_key`
WHERE lt._litter_key = %s
"""
@app.route('/api/litter.json')
@login_required
def get_litter_detail():
    """
    return litter detail including mating history
    """
    lk = request.args.get('lk')

    js = cache_get('api_litter.json_%s' % lk)
    if js:
        return Response(js, status=200, mimetype='application/json')

    parents_row = query_db(SQL_MOUSE_LITTER, (lk,), one=True)
    lt_comment,sire,dam1,dam2,dob,wean,born,lt_id = [x for x in parents_row]
    parents = [m for m in (sire,dam1,dam2) if m]
    rows = query_db('SELECT _mouse_key from Mouse WHERE _litter_key=%s', (lk,))
    siblings = [r[0] for r in rows]
    mice_keys = [m for m in parents]
    mice_keys.extend(siblings)

    dob = dob.strftime('%Y-%m-%d')
    wean = wean.strftime('%Y-%m-%d')
    mice = get_manymice(mice_keys)
    res = {'siblings': siblings, 'parents': parents, 'mice': mice,
           'comment': lt_comment, 'litterID': lt_id,
           'dob': dob, 'wean': wean, 'totalborn': born}
    js = dumps(res)
    cache_set('api_litter.json_%s' % lk, js)
    return Response(js, status=200, mimetype='application/json')



@app.route('/litter.html')
@login_required
def show_litter():

    return render_template('litter.html', user=g.user)


SQL_LITTER = '''
SELECT lt.litterID, st.strainName,lt.totalBorn, lt.birthDate,lt.comment,
       mt._dam1_key,mt._dam2_key,mt._sire_key,lt.weanDate,lt.numberBornDead
FROM
    (SELECT * FROM Litter WHERE Status='A' AND _litter_key NOT IN
        (SELECT DISTINCT _litter_key FROM Mouse WHERE _litter_key IS NOT NULL)
    ) lt
LEFT JOIN Mating mt on lt._mating_key=mt._mating_key
LEFT JOIN Strain st on mt._strain_key=st._strain_key
'''
@app.route('/api/litters.json')
@login_required
def get_litters():
    rows = query_db(SQL_LITTER)
    mating_mice = {}
    litters = []
    for r in rows:
        borndead = r[9] if r[9] else 0  # numberBornDead
        litter = {
                'id': r[0],
                'strain': r[1],
                'born': r[2] - borndead,
                'dob': r[3],
                'comment': r[4],
                'dam1': r[5],
                'dam2': r[6],
                'sire': r[7],
                'wean': r[8],
                }
        if litter['dob']:
            litter['dob'] = litter['dob'].strftime('%Y-%m-%d')

        if litter['wean']:
            litter['wean'] = litter['wean'].strftime('%Y-%m-%d')

        litters.append(litter)
        # deduplicate three mouse key( dam1, dam2, sire)
        for i in range(5,8):
            mating_mice[r[i]] = 1

    mice_keys = [m for m in mating_mice]
    fmt_str = ','.join(['%s'] * len(mice_keys))
    sql = ('SELECT m._mouse_key,m.ID,c.containerName FROM '
            '  (SELECT _mouse_key,ID,_pen_key FROM Mouse '
            '   WHERE _mouse_key IN (%s)) m '
           'LEFT JOIN Container c on c._container_key=m._pen_key ')

    rows = query_db(sql % fmt_str, tuple(mice_keys))

    mice = {}
    for r in rows:
        mk, tag, cage = r[0], r[1], r[2]
        mice[mk] = {'tag': tag, 'cage': cage}

    return jsonify({'mice': mice, 'litters': litters})



SQL_MICEINCAGE = """
SELECT MouseID,Sex,Strain,AgeInDays,Color,BreedingStatus,
       PenID,PenName,labSymbol,Genotype,DOB,MouseKey,MComment
FROM
(SELECT
    Mouse.ID as MouseID , Mouse.sex as Sex, Mouse._mouse_key as MouseKey,
    TIMESTAMPDIFF(DAY,Mouse.birthDate,CURDATE()) as AgeInDays,
    Mouse.birthDate as DOB,Mouse.comment as MComment,
    Mouse.breedingStatus as BreedingStatus , Strain.strainName as Strain ,
    Container.containerID as PenID , Container.containerName as PenName ,
    Mouse.coatColor as Color,
    Genotype._gene_key,
    CONCAT(Genotype.allele1, "/",Genotype.allele2) as Genotype
FROM Mouse
Left Join Strain On Strain.`_strain_key` = Mouse.`_strain_key`
Left Join Container On Container.`_container_key` = Mouse.`_pen_key`
Left Join Genotype on Genotype.`_mouse_key` = Mouse.`_mouse_key`
WHERE Mouse.lifeStatus = 'A' AND Mouse._pen_key='%s') m
LEFT JOIN Gene on Gene.`_gene_key` = m.`_gene_key`
"""
CMAP = {'Agouti':'AG', 'Black':'BL', 'White':'WH', 'Brown':'BR',
        'GreyWhit': 'GW'}
def get_cage_detail(cageid):
    ''' get cage name, rack location, mice detail for a given cage'''

    # TODO serial dict
    #c_cage = cache_get('get_cage_detail_%s' % cageid)
    #if c_cage:
    #    return c_cage

    sql = 'select _container_key,containerName from Container where containerID=%s'
    ck, cagename = query_db(sql, (cageid,), one=True)
    prot = '20040048AR'

    if not cagename:
        cagename = ''

    rack_name, rack_rowid, rack_colid, cn = extract_rack_location(cagename)

    cage = {'pi': cfg['pi'],
            'protocol': prot,
            'rack': rack_name,
            'cageloc': '%s%s' % (rack_rowid, rack_colid),
            'cagename': cn,
            'mice': []}

    rows = query_db(SQL_MICEINCAGE, (ck,))
    mice = {}
    for r in rows:
        mk = r[11]
        genotype = '%s %s' % (r[8], r[9])
        if mk in mice:
            mice[mk]['genotype'].append(genotype)
            continue

        mouse = {
                'tag': r[0],
                'sex': r[1],
                'strain': r[2],
                'age': r[3],
                'color': r[4],
                'breedingstatus': r[5],
                'cageid': r[6],
                'cagename': r[7],
                'genotype': [],
                'dob': r[10],
                'mk': r[11],
                'comment': r[12],
                }

        mouse['color'] = CMAP[mouse['color']]
        mouse['dob'] = mouse['dob'].strftime('%b-%d')
        mouse['genotype'].append(genotype)
        mice[mk] = mouse

    cage['mice'] = [mice[mk] for mk in mice]
    for m in cage['mice']:
        m['genotype'] = ', '.join(m['genotype'])
    return cage


@app.route('/api/print-cagecards', methods=['POST'])
@login_required
def print_cagecards():
    cageids = request.get_json()

    cages = []
    for cageid in cageids:
        cage = get_cage_detail(cageid)
        cages.append(cage)

    tex = cagecard_gen(cages)
    tmptex = os.path.join(APP_TMP, 'cagecard_tmp.tex')
    tmppdf = os.path.join(APP_TMP, 'cagecard_tmp.pdf')
    with open(tmptex, 'w') as f:
        f.write(tex)

    arg = ('xelatex', tmptex)
    p = subprocess.Popen(arg, cwd=APP_TMP)

    output, err = p.communicate()
    p_status = p.wait()
    #if p.returncode != 0:
    #    pass
    #else:

    return send_file(tmppdf)


def cagecard_gen(cages):
    template = latex_jinja_env.get_template('cagecard.tex')
    tex = template.render(cages=cages)
    return tex


def main():
    app.run(host=cfg['host'], port=cfg['port'])


if __name__ == "__main__":
    main()
