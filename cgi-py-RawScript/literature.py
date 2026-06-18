#!/usr/bin/python3
# -*- coding: utf-8 -*-

import cgi
import cgitb
import pymysql
import json
import os
import sys

# 开启调试模式
cgitb.enable()

# ================= 配置加载 =================
def load_db_config():
    # 强制指定配置文件路径
    config_path = '/var/www/html/literature/config.json'
    
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            conf = json.load(f)
            return conf['database']
    else:
        return {}

# ================= 数据库连接 =================
def get_db_connection():
    conf = load_db_config()
    try:
        # 使用 pymysql 连接
        db = pymysql.connect(
            host=conf.get('host', 'localhost'),
            user=conf.get('user', 'root'),
            password=conf.get('password', ''),
            database=conf.get('db_name', 'wheatomics_db'),
            charset='utf8mb4'
        )
        return db
    except Exception as e:
        print("Content-Type: text/html; charset=utf-8")
        print("<h3>Database Connection Error</h3>")
        print("<p>%s</p>" % str(e))
        sys.exit()

# ================= 辅助函数 =================
def get_paper_tags(cursor, pmid):
    """获取单篇文章的所有标签"""
    sql = "SELECT tag_name FROM paper_tags WHERE pmid = %s"
    cursor.execute(sql, (pmid,))
    results = cursor.fetchall()
    
    tags_html = ""
    for r in results:
        tag = r[0]
        color_class = "badge-info" 
        tag_lower = tag.lower()
        
        if "rust" in tag_lower or "mildew" in tag_lower or "fusarium" in tag_lower:
            color_class = "badge-danger"
        elif "yield" in tag_lower or "weight" in tag_lower or "grain" in tag_lower:
            color_class = "badge-success"
        elif "drought" in tag_lower or "heat" in tag_lower:
            color_class = "badge-warning"
            
        tags_html += '<a href="?tag=%s" class="badge %s mr-1" style="font-size: 12px; padding: 5px 8px;">%s</a> ' % (tag, color_class, tag)
    return tags_html

# ================= 页面头部输出 =================
# 注意：这里必须紧接着输出空行
print("Content-Type: text/html; charset=utf-8")
print("")

print('<!DOCTYPE html>')
print('<html xmlns="http://www.w3.org/1999/xhtml">')
print('<head>')
print('<title>Wheat Literature Hub</title>')
print('<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />')
print('<link rel="shortcut icon" href="/favicon.ico" type="image/x-icon" />')
# CSS
print('<link rel="stylesheet" href="/css/style.css" type="text/css" />')
print('<link rel="stylesheet" href="/css/bootstrap-4.5.3-dist/css/bootstrap.css" type="text/css" />')
# JS
print('<script src="/js/jquery/1.9.1/jquery.min.js" type=text/javascript></script>')
print('<script src="/css/bootstrap-4.5.3-dist/js/bootstrap.js" type=text/javascript></script>')

# 自定义 CSS
print('''
<style>
    .paper-card {
        border-left: 4px solid #007DBC;
        background-color: #f9f9f9;
        margin-bottom: 20px;
        padding: 15px;
        border-radius: 4px;
        transition: all 0.3s;
    }
    .paper-card:hover {
        background-color: #fff;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }
    .journal-meta {
        color: #666;
        font-size: 0.9em;
        margin-bottom: 5px;
    }
    .paper-title {
        font-size: 1.2em;
        font-weight: bold;
        color: #333;
        text-decoration: none;
    }
    .paper-title:hover {
        color: #007DBC;
        text-decoration: underline;
    }
    .authors {
        color: #555;
        font-size: 0.95em;
        margin-bottom: 8px;
        font-style: italic;
    }
    .abstract-box {
        margin-top: 10px;
        font-size: 0.95em;
        color: #444;
        display: none;
        padding: 10px;
        background: #fff;
        border: 1px solid #eee;
    }
    .sidebar-section {
        margin-bottom: 30px;
    }
</style>
''')

print('<script> $(function(){ $("#header").load("/header.html"); }); </script>')
print('<script> $(function(){ $("#footer").load("/footer.html"); }); </script>')
print('''
<script>
function toggleAbstract(id) {
    $("#abs-" + id).slideToggle();
}
</script>
''')
print('</head>')
print('<body>')
print('<div id="header"></div>')

# ================= 主体内容 =================
print('<div id="home_content" class="container" style="margin-top: 20px; min-height: 600px;">')

form = cgi.FieldStorage()
search_query = form.getvalue("search", "").strip()
tag_query = form.getvalue("tag", "").strip()

conn = get_db_connection()
cursor = conn.cursor()

# 标题
print('<div class="row mb-4">')
print('<div class="col-md-12">')
print('<h3 style="border-bottom: 2px solid #007DBC; padding-bottom: 10px;">🌾 Wheatomics Literature Hub</h3>')
print('</div></div>')

print('<div class="row">')

# --- 左侧栏 ---
print('<div class="col-md-3">')

# 搜索
print('<div class="sidebar-section">')
print('<h5>Search</h5>')
print('<form action="literature.py" method="GET">')
print('<div class="input-group">')
print('<input type="text" name="search" class="form-control" placeholder="Title/Abstract..." value="%s">' % search_query)
print('<div class="input-group-append">')
print('<button class="btn btn-primary" type="submit">Go</button>')
print('</div></div>')
print('</form>')
print('</div>')

# 热门标签
print('<div class="sidebar-section">')
print('<h5>Popular Traits</h5>')
try:
    tag_sql = "SELECT tag_name, COUNT(*) as c FROM paper_tags GROUP BY tag_name ORDER BY c DESC LIMIT 20"
    cursor.execute(tag_sql)
    tags = cursor.fetchall()
    print('<div class="d-flex flex-wrap">')
    for t in tags:
        # pymysql 默认返回 tuple，除非设置 DictCursor，这里用 tuple 索引
        t_name = t[0]
        t_count = t[1]
        print('<a href="?tag=%s" class="badge badge-light border mr-1 mb-1">%s (%s)</a>' % (t_name, t_name, t_count))
    print('</div>')
except:
    print("No tags found.")
print('</div>')

# 导航
print('<div class="sidebar-section">')
print('<h5>Navigation</h5>')
print('<ul class="list-group">')
print('<li class="list-group-item"><a href="literature.py">📅 Latest Updates</a></li>')
print('</ul>')
print('</div>')

print('</div>') # End Left Column

# --- 右侧内容 ---
print('<div class="col-md-9">')

sql_base = "SELECT pmid, title, journal, pub_date, authors, abstract, link FROM papers "
params = []
limit_clause = " ORDER BY created_at DESC LIMIT 50"
filter_desc = "Latest Updates"

if search_query:
    sql = sql_base + "WHERE title LIKE %s OR abstract LIKE %s" + limit_clause
    search_param = "%" + search_query + "%"
    params = [search_param, search_param]
    filter_desc = 'Search results for: "<span class="text-primary">%s</span>"' % search_query

elif tag_query:
    sql = "SELECT p.pmid, p.title, p.journal, p.pub_date, p.authors, p.abstract, p.link FROM papers p JOIN paper_tags t ON p.pmid = t.pmid WHERE t.tag_name = %s" + limit_clause
    params = [tag_query]
    filter_desc = 'Papers tagged with: "<span class="text-success">%s</span>"' % tag_query

else:
    sql = sql_base + limit_clause

print('<div class="alert alert-secondary">%s</div>' % filter_desc)

try:
    cursor.execute(sql, tuple(params))
    papers = cursor.fetchall()

    if not papers:
        print('<div class="alert alert-warning">No papers found matching your criteria.</div>')
    
    for row in papers:
        pmid = row[0]
        title = row[1]
        journal = row[2]
        date = row[3]
        authors = row[4]
        abstract = row[5]
        link = row[6]

        tags_html = get_paper_tags(cursor, pmid)

        auth_list = authors.split(',')
        if len(auth_list) > 6:
            authors_display = ", ".join(auth_list[:5]) + " ... " + auth_list[-1]
        else:
            authors_display = authors

        print('<div class="paper-card">')
        print('<div class="journal-meta">📖 <b>%s</b> | 📅 %s | PMID: %s</div>' % (journal, date, pmid))
        print('<div><a href="%s" target="_blank" class="paper-title">%s</a></div>' % (link, title))
        print('<div class="authors">%s</div>' % authors_display)
        
        if tags_html:
            print('<div class="mb-2">%s</div>' % tags_html)
        
        print('<button class="btn btn-sm btn-outline-secondary" onclick="toggleAbstract(\'%s\')">Show Abstract</button>' % pmid)
        print('<div id="abs-%s" class="abstract-box">%s</div>' % (pmid, abstract))
        print('</div>')

except Exception as e:
    print('<div class="alert alert-danger">Error executing query: %s</div>' % str(e))

cursor.close()
conn.close()

print('</div>') # End Right Column
print('</div>') # End Row
print('</div>') # End Container
print('<div id="footer"></div>')
print('</body>')
print('</html>')
