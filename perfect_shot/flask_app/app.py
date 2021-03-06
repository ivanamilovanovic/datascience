#!/usr/bin/python3

from __future__ import division, print_function
# coding=utf-8
import sys
import os
import glob
import re
import numpy as np
import operator
import json
#import logging

# # Keras
# from keras.models import load_model
# from keras.preprocessing import image
# from keras.applications.imagenet_utils import decode_predictions

# Flask utils
from flask import Flask, redirect, url_for, request, render_template, jsonify
from werkzeug.utils import secure_filename
from gevent.pywsgi import WSGIServer

#
# Import modules from parent folder
#
import inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0,parentdir)

import ranker
import feature_extraction

MODEL_PATH = "../ranker_out/dataset/global_faces_m_ec/model.pickle"

# Define a flask app
app = Flask(__name__)
# Load trained model
model = ranker.load_model(MODEL_PATH)
# model._make_predict_function()  # Necessary
print('Model loaded. Check http://127.0.0.1:5000/')


def index_of_item_with_substring(strings_list, substring):
    for i in range(0, len(strings_list)):
        if substring in strings_list[i]:
            return i
    return -1


def model_predict(img_paths, model):
    print("PREDICTION")
    print(img_paths)
    feat_df = feature_extraction.img_list_to_features(img_paths, debug_output=None)
    dataset = ranker.create_set(feat_df, model['args'])
    ranker.ImageSample.clf = model['classifier']
    ranker.ImageSample.scaler = model['scaler']
    sorted_dataset = sorted(dataset, reverse=True)

    print(sorted_dataset)

    sorted_ids = []
    print(img_paths)
    for i in range(0, len(sorted_dataset)):
        im_sample = sorted_dataset[i]
        print("%d\t%s" % (i, im_sample.im_path))
        im_sample_index = index_of_item_with_substring(img_paths, os.path.basename(im_sample.im_path))
        assert im_sample_index != -1
        sorted_ids.append(im_sample_index)

    print()
    for id in sorted_ids:
        print("%d\t%s" % (id, img_paths[id]))

    return sorted_ids


@app.route('/', methods=['GET'])
def index():
    # Main page
    print("=== APP ROUTE /")
    return render_template('index.html')


@app.route('/predict', methods=['GET', 'POST'])
def upload():
    print("=== APP ROUTE PREDICT")
    if request.method == 'POST':
        print("post")
        file_paths = []
        files_dict = request.files.to_dict(flat=False)
        for f in files_dict['file']:
            basepath = os.path.dirname(__file__)
            file_path = os.path.join(
                basepath, 'uploads', secure_filename(f.filename))
            f.save(file_path)
            file_paths.append(file_path)

        result = model_predict(file_paths, model)
        return jsonify({'payload':json.dumps(result)})

    return None


#@app.route('/', defaults={'path': ''})
#@app.route('/<path:path>')
#def catch_all(path):
#    print('=== You want path: %s' % path)
#    return '=== You want path: %s' % path


if __name__ == '__main__':
    # Serve the app with gevent
    http_server = WSGIServer(('', 5000), app)
    http_server.serve_forever()
