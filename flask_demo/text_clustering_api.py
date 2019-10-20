import os
import secrets

from io import BytesIO
import time
import zipfile

from stemming.porter2 import stem
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.cluster import KMeans

from flask import Flask, render_template, request, redirect, url_for, send_file, make_response
from flask_wtf import FlaskForm
from wtforms import IntegerField, MultipleFileField, SubmitField
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms.validators import DataRequired
from werkzeug.utils import secure_filename
from flasgger import Swagger

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(15)
swagger = Swagger(app)

class ModelInputForm(FlaskForm):
    no_of_clusters = IntegerField("No of clusters:", default=2, validators=[DataRequired()])
    input_file = FileField("Input file:" , validators=[FileRequired(), FileAllowed(['txt', 'csv'], 'Txt or csv only!')])
    submit = SubmitField('Submit')

def cleanse_text(text):
    if text:       
        # whitespaces and stemming
        red_text = [stem(word) for word in text.split()]
        return ' '.join(red_text)
    else:
        return text

def cluster_text(input_file, no_of_clusters):
    no_of_clusters = int(no_of_clusters)
    unstructure = 'text' # col name
    data = pd.read_csv(input_file)
    data = data.fillna('NULL')

    data['clean_sum'] = data[unstructure].apply(cleanse_text)

    # vectorize into term-document matrix
    vectorizer = CountVectorizer(analyzer='word', stop_words='english')
    counts = vectorizer.fit_transform(data['clean_sum'])

    # cluster
    kmeans = KMeans(n_clusters=no_of_clusters)
    data['cluster_num'] = kmeans.fit_predict(counts)

    data = data.drop(['clean_sum'], axis=1)

    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    workbook = writer.book
    data.to_excel(writer, sheet_name='Clusters', 
                    encoding='utf-8', index=False)
    clusters_sheet = writer.sheets['Clusters']
    clusters_sheet.set_column('C:C', 12.5)
    clusters_sheet.set_column('B:B', 50, workbook.add_format({'text_wrap': True}))

    # finding top keywords for each cluster
    clusters = []
    for i in range(np.shape(kmeans.cluster_centers_)[0]):
        data_cluster = pd.concat([
        pd.Series(vectorizer.get_feature_names()), 
        pd.DataFrame(kmeans.cluster_centers_[i])], 
        axis=1)
        data_cluster.columns = ['keywords', 'weights']
        data_cluster = data_cluster.sort_values(by='weights', ascending=False)
        data_clust = data_cluster.head(n=10)['keywords'].tolist()
        clusters.append(data_clust)
    pd.DataFrame(clusters).to_excel(writer, sheet_name='Top_Keywords', startrow=1, encoding='utf-8')
    top_keyword_sheet = writer.sheets['Top_Keywords']
    merge_format = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'bold': True})
    top_keyword_sheet.merge_range('A1:A2', 'cluster_num', merge_format)
    top_keyword_sheet.merge_range('B1:K1', 'top_keyword', merge_format)
    for i in range(1,11):
        top_keyword_sheet.write_number(row=1, col=i, number=i)
    top_keyword_sheet.set_column('A:A', 12.5)
    top_keyword_sheet.conditional_format('A1:K{}'.format(no_of_clusters+2), {'type':'no_blanks', 'format': workbook.add_format({'border':1})})
    top_keyword_sheet.conditional_format('A1:K{}'.format(no_of_clusters+2), {'type':'blanks', 'format': workbook.add_format({'border':1})})

    # pivot number of documents in each cluster
    data_pivot = data.groupby(['cluster_num'], as_index=False).size()
    data_pivot.name = 'num_documents'
    data_pivot = data_pivot.reset_index()
    data_pivot.to_excel(writer, sheet_name='Cluster_Report', encoding='utf-8', index=False)

    # insert chart
    cluster_report_sheet = writer.sheets['Cluster_Report']
    chart = workbook.add_chart({'type': 'column'})
    chart.add_series({'categories': '=Cluster_Report!$A$2:$A{}'.format(no_of_clusters+1), 'values': '=Cluster_Report!$B$2:$B{}'.format(no_of_clusters+1)})
    chart.set_legend({'none': True})
    chart.set_x_axis({'name': 'cluster_num'})
    chart.set_y_axis({'name': '# Documents'})
    cluster_report_sheet.insert_chart('D2', chart)
    cluster_report_sheet.set_column('A:A', 12.5)
    cluster_report_sheet.set_column('B:B', 17)

    writer.save()

    # in case want to output multiple files --> convert to a downloadable zip file
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        names = ['cluster_output.xlsx'] # 
        files = [output] # length of names and files should be the same
        for i in range(len(files)):
            data = zipfile.ZipInfo(names[i])
            data.date_time = time.localtime(time.time())
            data.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(data, files[i].getvalue())
    memory_file.seek(0)
    return memory_file

@app.route('/')
def index():
    return render_template('02-home.html')

@app.route('/ml_models', methods=['GET', 'POST'])
def ml_models():
    form = ModelInputForm()
    if form.validate_on_submit():
        no_of_clusters = form.no_of_clusters.data
        # filename = secure_filename(form.input_file.data.filename)
        # form.input_file.data.save('uploads/' + filename)
        input_file = form.input_file.data
        memory_file = cluster_text(input_file, no_of_clusters)

        return send_file(
                memory_file, 
                as_attachment=True, 
                attachment_filename='cluster_output.zip')

    return render_template('03-ml_models.html', form=form)

@app.route('/text_clustering_api', methods=['POST'])
def text_clustering_api():
    """
    This API will help you generate clusters based on keywords present in unstructured text
    Call this api passing the following parameters - 
        Dataset Path - <hostname>\\<path to dataset>
        Number of Clusters
    ---
    tags:
      - Text Clustering API
    parameters:
      - name: input_file
        in: formData
        type: file
        required: true
        description: The fully qualified path of the dataset without the extension.
      - name: no_of_clusters
        in: query
        type: integer
        required: true
        description: The number of clusters
        default: 2
    produces:
      application/octet-stream
    responses:
      200:
        description: Text clustering result
        schema:
          type: file
    """
    no_of_clusters = request.args.get('no_of_clusters')
    input_file = request.files.get('input_file')
    memory_file = cluster_text(input_file, no_of_clusters)

    # # xlsx
    # save_path = 'cluster_output.xlsx'
    # response = make_response(send_file(save_path))
    # response.headers['Content-Disposition'] = 'attachment;filename=cluster_output.xlsx'

    # zip
    response = make_response(send_file(memory_file, as_attachment=True, attachment_filename='cluster_output.zip'))
    response.headers['Content-Disposition'] = 'attachment;filename=cluster_output.zip'
    
    response.headers['Access-Control-Allow-Origin'] = '*' # to allow communication from different IP address
    return response

@app.route('/confiding')
def confiding():
    return render_template('04-confiding.html')

@app.route('/about')
def about():
    return render_template('05-about.html')

if __name__=='__main__':
    app.run()