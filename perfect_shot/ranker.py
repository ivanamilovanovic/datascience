import os
import itertools
import numpy as np
import argparse
from scipy import stats
import pylab as pl
import cv2
from sklearn import svm, linear_model
from sklearn.model_selection import train_test_split
import pandas as pd
from sys import stdout
import shutil


# construct the argument parser and parse the arguments
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", required=True, help="Input CSV dataset file")
    parser.add_argument("-l", "--labels", required=True, help = "Input CSV labels file")
    parser.add_argument("-o", "--output", required=True, help="Output folder")
    parser.add_argument("-di", "--debug-images", required=False, help="Debug images")
    parser.add_argument("--force", action="store_true", help="Overwrites output folder if it already exists")
    return parser.parse_args()


#
# Converts one row of feature.csv table into feature vector
#
def row_to_feature_vector(dataFrame, row_id):
    # sharpness
    # noise
    # motion_blur
    # contrast
    # saturation
    # lines
    # symmetry
    # faces
    # number_of_faces
    # faces_sharp_all
    # faces_noise_all
    # faces_motion_blur_all
    # closed_eyes
    fv = []
    fv.append(dataFrame.sharpness[row_id])
    fv.append(dataFrame.noise[row_id])
    fv.append(dataFrame.motion_blur[row_id])
    return fv


#
# Reads labels CSV into dictonary mapping im_path to (label, set) pair
#
def read_labels(path, label2id):
    img2label_and_set = {}
    lab_df = pd.read_csv(args.labels, ',')
    for row_id in range(0, len(lab_df.im_path)):
        im_path = lab_df.im_path[row_id]
        assert im_path not in img2label_and_set
        img2label_and_set[im_path] = (label2id[lab_df.label[row_id]], lab_df.set_name[row_id])
    return img2label_and_set


#
# Class representing information about image: feature vector, label and im_path
#
class ImageSample:
    clf = None

    def __init__(self, X, y, im_path):
        self.X = X
        self.y = y
        self.im_path = im_path

    def __str__(self):
        return "\t".join([self.im_path, str(self.y), str(self.X)])

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return True

    def __lt__(self, other):
        return ImageSample.clf.predict([self.X + other.X])[0] == -1

    def __le__(self, other):
        return self.__lt__(other)

    def __gt__(self, other):
        return ImageSample.clf.predict([self.X + other.X])[0] == 1

    def __ge__(self, other):
        return self.__gt__(other)

#    def __repr__(self):
#        return str(self)


#
# Creates collections of ImageSamples for each unique set
#
def create_sets(feat_df, img2label_and_set):
    set_name2image_samples = {}
    for row_id in range(0, len(feat_df.im_path)):
        im_path = feat_df.im_path[row_id]
        if not im_path in img2label_and_set:
            print("Skipping %s because label was not found" % im_path)
            continue
        label, set_name = img2label_and_set[im_path]

        X = row_to_feature_vector(feat_df, row_id)

        if not set_name in set_name2image_samples:
            set_name2image_samples[set_name] = []
        set_name2image_samples[set_name].append(ImageSample(X, label, im_path))

    return set_name2image_samples


#
# For debugging purposes
#
def print_sets(set_name2image_samples):
    for set_name in set_name2image_samples.keys():
        print(set_name)
        for img_sample in set_name2image_samples[set_name]:
            print("\t", str(img_sample))
        print()


#
# Converts list of feature vectors and labels into
# list of feature vector pairs (concatenatin) and diff labels.
#
# X, y - input feature vectors and labels
# Xp, yp - output pairwise transformed feature vectors and labels
#
def pairwise_transform(X, y, Xp, yp):
    assert len(X) == len(y)
    assert len(Xp) == len(yp)

    comb = itertools.combinations(range(len(X)), 2)
    for (i,j) in comb:
        # skip equal labels because we don't have equal diff class
        if y[i] == y[j]:
            continue

        # note: + is list concatenation
        Xp.append(X[i] + X[j])
        yp.append(np.sign(y[i] - y[j]))

        # reverse order for balanced classes
        Xp.append(X[j] + X[i])
        yp.append(np.sign(y[j] - y[i]))


def sets2pairwise(set_image_samples):
    Xp = []
    yp = []
    for set_name, image_samples in set_image_samples:
        set_X = []
        set_y = []
        for image_sample in image_samples:
            set_X.append(image_sample.X)
            set_y.append(image_sample.y)
        pairwise_transform(set_X, set_y, Xp, yp)
    return Xp, yp


def filter_dummy(set_name2image_samples):
    keys = list(set_name2image_samples.keys())
    for key in keys:
        all_0 = True
        all_1 = True
        for item in set_name2image_samples[key]:
            if item.y == 0:
                all_1 = False
            else:
                all_0 = False
        if all_0:
            print("Filtering set %s because all images are DISCARD" % key)
            del set_name2image_samples[key]
        if all_1:
            print("Filtering set %s because all images are KEEP" % key)
            del set_name2image_samples[key]


def basic_sort(in_list):
    r = list(in_list)
    for i in range(0, len(r)):
        for j in range(i + 1, len(r)):
            if r[i] < r[j]:
                t = r[j]
                r[j] = r[i]
                r[i] = t
    return r


def score_top_1(set2sorted):
    correct = 0
    for set_name, image_samples in set2sorted.items():
        if image_samples[0].y == 1:
            correct += 1
    return float(correct) / len(set2sorted)


def write_ranker_output_file(file_path, set2sorted):
    # write ranked sets to output input_folder
    with open(file_path, 'w') as out_file:
        for set_name, sorted_images in set2sorted.items():
            out_file.write(str(set_name))
            out_file.write("\n")
            for image in sorted_images:
                out_file.write("\t".join(["", str(image)]))
                out_file.write("\n")


def dump_errors(set2sorted, debug_images_folder, debug_folder):
    os.makedirs(debug_folder)
    for set_name, image_samples in set2sorted.items():
        set_name = str(set_name)
        if image_samples[0].y == 0:
            set_folder = os.path.join(debug_folder, set_name)
            os.makedirs(set_folder)

            predicted_src = os.path.join(debug_images_folder, image_samples[0].im_path + "_debug.png")
            predicted_filename = os.path.basename(predicted_src)
            predicted_dst = os.path.join(debug_folder, set_name, "pred_" + predicted_filename)
            shutil.copyfile(predicted_src, predicted_dst)

            for image_sample in image_samples:
                print(image_sample)
                if image_sample.y == 1:
                    print("WRONG")
                    labeled_src = os.path.join(debug_images_folder, image_sample.im_path + "_debug.png")
                    labeled_filename = os.path.basename(labeled_src)
                    labeled_dst = os.path.join(debug_folder, set_name, "lab_" + labeled_filename)
                    shutil.copyfile(labeled_src, labeled_dst)


label2id = {"discard": 0, "keep": 1}




if __name__ == "__main__":
    np.random.seed(31415)

    args = parse_args()

    #create output folder
    if os.path.exists(args.output) and not args.force:
        print("Output folder %s already exists! Use --force to override this check." % (args.output))
        exit()
    if os.path.exists(args.output):
        shutil.rmtree(args.output)
    os.makedirs(args.output)

    with open(os.path.join(args.output, "output.txt"), "w") as output_file:
        output_file.write(str(args))

        # load labels
        img2label_and_set = read_labels(args.labels, label2id)

        # featurize
        feat_df = pd.read_csv(args.input)
        set_name2image_samples = create_sets(feat_df, img2label_and_set)
        filter_dummy(set_name2image_samples)
        print_sets(set_name2image_samples)


        # training/test split
        set_image_sample_items = list(set_name2image_samples.items())
        train, test = train_test_split(set_image_sample_items, test_size=0.5)

        # transform training into pairwise classification problem
        Xp_train, yp_train = sets2pairwise(train)
        Xp_test, yp_test = sets2pairwise(test)

        clf = svm.SVC(kernel='linear', C=.1, verbose=True)
        clf.fit(Xp_train, yp_train)
        stdout.write("\n\n")
        stdout.write("train accuracy: %.2f%%\n" % (100.0 * clf.score(Xp_train, yp_train)))
        stdout.write("test accuracy: %.2f%%\n" % (100.0 * clf.score(Xp_test, yp_test)))
        output_file.write("\n\n")
        output_file.write("train accuracy: %.2f%%\n" % (100.0 * clf.score(Xp_train, yp_train)))
        output_file.write("test accuracy: %.2f%%\n" % (100.0 * clf.score(Xp_test, yp_test)))


        # set reference to classifier so that we can use comparison methods on ImageSample
        ImageSample.clf = clf

        # rank all sets in training
        set2sorted_train = {}
        for set_name, image_samples in train:
            set2sorted_train[set_name] = sorted(image_samples, reverse=True)

        #rank all sets in test
        set2sorted_test = {}
        for set_name, image_samples in test:
            set2sorted_test[set_name] = sorted(image_samples, reverse=True)

        # write ranked sets to output input_folder
        write_ranker_output_file(os.path.join(args.output, "ranked_test.txt"), set2sorted_test)
        write_ranker_output_file(os.path.join(args.output, "ranked_train.txt"), set2sorted_train)

        stdout.write("\n\n")
        stdout.write("train top1: %.2f%%\n" % (100 * score_top_1(set2sorted_train)))
        stdout.write("test top1: %.2f%%\n" % (100 * score_top_1(set2sorted_test)))
        output_file.write("\n\n")
        output_file.write("train top1: %.2f%%\n" % (100 * score_top_1(set2sorted_train)))
        output_file.write("test top1: %.2f%%\n" % (100 * score_top_1(set2sorted_test)))

        # collect correct / incorrect classification pairs
        if args.debug_images:
            dump_errors(set2sorted_test, args.debug_images, os.path.join(args.output, "test_debug"))
            dump_errors(set2sorted_train, args.debug_images, os.path.join(args.output, "train_debug"))
