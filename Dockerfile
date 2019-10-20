# base image
FROM continuumio/miniconda3
LABEL MAINTAINER="Eltina Hutahaean"
EXPOSE 8000

# # load in the environment.yml file
# ADD environment.yml /
# # create the environment
# RUN conda env create -f environment.yml
# # Pull the environment name out of the environment.yml
# RUN echo "source activate $(head -1 environment.yml | cut -d' ' -f2)" > ~/.bashrc
# ENV PATH /opt/conda/envs/$(head -1 environment.yml | cut -d' ' -f2)/bin:$PATH

ENV PY_SCI_PACKAGES="\
    numpy \
    scikit-learn \
    pandas \
    "
ENV PYTHONDONTWRITEBYTECODE=true
RUN conda install --yes --freeze-installed nomkl $PY_SCI_PACKAGES \
    && conda clean -afy \
    && find /opt/conda/ -follow -type f -name '*.a' -delete \
    && find /opt/conda/ -follow -type f -name '*.pyc' -delete \
    && find /opt/conda/ -follow -type f -name '*.js.map' -delete

# install server packages 
ENV EXTRA_PACKAGES="\
    apache2 \
    apache2-dev \
    vim \
    "
RUN apt-get update && apt-get install -y $EXTRA_PACKAGES \
    && apt-get clean \
    && apt-get autoremove \
    && rm -rf /var/lib/apt/lists/*

# specify working directory
WORKDIR /var/www/text_clustering_api/
COPY ./flask_demo /var/www/text_clustering_api/
COPY ./text_clustering_api.wsgi /var/www/text_clustering_api/text_clustering_api.wsgi

# install non-conda packages
RUN pip install -r requirements.txt

# fire up the app
RUN /opt/conda/bin/mod_wsgi-express install-module
RUN mod_wsgi-express setup-server text_clustering_api.wsgi --port=8000 \
    --user www-data --group www-data \
    --server-root=/etc/mod_wsgi-express-80
CMD /etc/mod_wsgi-express-80/apachectl start -D FOREGROUND