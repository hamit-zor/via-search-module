"""Script to be used for query by example."""
if __name__ == "__main__":
    import time
    start_time = time.time() * 1000

    from modules import args, stdout, video, feature as feature_module, filesystem
    from modules.database import database
    import cv2
    import numpy as np
    import ujson
    import json
    import os

    parser = args.parser

    parser.add_argument(
        "video_id", type=int, help="VideoId of the video that example will search inside")
    parser.add_argument(
        "example_file", help="Example image file to search inside the video")
    parser.add_argument("-m", "--min", type=float,
                        help="minimum good features to reckon as match percentage: [0,1]", default=0.33)
    parser.add_argument("-w", "--wait", type=float,
                        help="duration of showing successful matches in seconds", default=1.0)

    # load command line arguments
    args = parser.parse_args()

    stdout = stdout.Stdout(args.api or args.quiet)

    video_meta = database.get_video(args.video_id)

    video_format = video_meta[4]
    video_blob = video_meta[7]
    video_fps = video_meta[8]
    video_total_frame = video_meta[9]

    # read query image
    query_image = cv2.imread(args.example_file, 0)

    # extract features from query image
    query_features = feature_module.extract(query_image)

    video_cap_display = None
    temp_file_path = None

    if args.display:
        # read video blob and write into filesystem
        temp_file_path = filesystem.write_base64(
            video_blob, video_format)
        # read video for display purposes
        video_cap_display = cv2.VideoCapture(temp_file_path)

    # list that holds matches
    find = []

    def find_matches(frame_no, _):
        # get features between specied frame_no and frame_no + specified skip number
        features = database.get_features(args.video_id, frame_no)
        if features:
            # container for formatted key points
            kp = []
            # container for formatted descriptors
            des = []

            # iterate over these features for formatting purposes
            for feature in features:
                key_point = cv2.KeyPoint()
                key_point.pt = (feature[0], feature[1])
                kp.append(key_point)
                # decode json encoded list and append to des container
                des.append(ujson.loads(feature[2]))

            # cast list to numpy array for matching purposes
            des = np.asarray(des, np.float32)

            # create a tuple of key points and descriptor with corresponding indices for matching
            feature_set = (kp, des)

            # use frame.match function for matching and collect good matches
            good = feature_module.match(query_features[1], feature_set[1])

            # if number of good matches is greater than specified percentage of total number of features consider them as real match
            if len(good) > int(len(query_features[0]) * args.min):
                pts, mask = feature_module.get_homography_points(
                    query_features[0], feature_set[0], good, query_image)

                # save frame no and coordinates
                find.append(
                    {"frame_no": frame_no, "corners": (pts[0][0].tolist(), pts[1][0].tolist(), pts[2][0].tolist(), pts[3][0].tolist())})

                if args.display:
                    # skip video file to the frame that match was found
                    video_cap_display.set(cv2.CAP_PROP_POS_FRAMES, frame_no)

                    # read the frame
                    _, frame = video_cap_display.read()

                    matchesMask = mask.ravel().tolist()

                    draw_params = dict(matchColor=(0, 255, 0),  # draw matches in green color
                                       singlePointColor=None,
                                       matchesMask=matchesMask,  # draw only inliers
                                       flags=2)

                    frame = cv2.polylines(
                        frame, [np.int32(pts)], True, 255, 3, cv2.LINE_AA)
                    # draw matches with calculated parameters above
                    if args.display_features:
                        frame = cv2.drawMatches(
                            query_image, query_features[0], frame, feature_set[0], good, None, **draw_params)

                    # show frame
                    cv2.imshow("Frame - " + str(frame_no), frame)
                    cv2.waitKey(int(args.wait * 1000))
                    cv2.destroyAllWindows()

    stdout.write("Searching %s in video with id = %s" %
                 (args.example_file, args.video_id))

    apply_params = dict(
        operation=find_matches,
        skip_amount=args.skip,
        begin=args.begin,
        end=args.end,
        info_function=stdout.progres_info
    )
    # call video.apply with specified video file with specified parameters
    video.apply(None, video_total_frame, video_fps, **apply_params)

    if not args.display:
        if not args.api:
            print "\n"
        print json.dumps(find, indent=3)

    if args.display:
        os.remove(temp_file_path)
    stdout.passed_time(start_time, "Finished in")
    exit(0)
