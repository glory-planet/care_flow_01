import os
from unittest.mock import MagicMock, patch

from video_analyzer import analyze_video, delete_video_file, download_video


def test_download_video_creates_parent_dir_and_calls_urlretrieve(tmp_path):
    dest = str(tmp_path / "nested" / "out.mp4")
    with patch("video_analyzer.urllib.request.urlretrieve") as mock_retrieve:
        result = download_video("https://example.com/video.mp4", dest)

    mock_retrieve.assert_called_once_with("https://example.com/video.mp4", dest)
    assert result == dest
    assert os.path.isdir(os.path.dirname(dest))


def test_analyze_video_returns_pose_detected_true_and_final_value(tmp_path):
    # MagicMock()은 모든 속성에 응답하므로 get_tracker_value()의 hasattr(tracker, "elapsed")
    # 분기가 항상 True로 오판된다 — spec으로 count/update만 갖게 제한한다.
    fake_tracker = MagicMock(spec=["count", "update"])
    fake_tracker.count = 7

    with patch("video_analyzer.build_trackers", return_value={"1": fake_tracker}), \
         patch("video_analyzer.PoseDetector") as MockDetector, \
         patch("video_analyzer.cv2.VideoCapture") as MockCapture:
        mock_detector = MockDetector.return_value
        # Two frames with landmarks, then end of video
        mock_detector.detect.side_effect = [[(0, 0, 0, 1.0)], [(0, 0, 0, 1.0)]]

        mock_cap = MockCapture.return_value
        mock_cap.read.side_effect = [(True, "frame1"), (True, "frame2"), (False, None)]

        result = analyze_video(str(tmp_path / "video.mp4"), "1")

    assert result == {"pose_detected": True, "final_value": 7}
    fake_tracker.update.assert_called()
    mock_detector.close.assert_called_once()
    mock_cap.release.assert_called_once()


def test_analyze_video_returns_pose_detected_false_when_no_landmarks_found(tmp_path):
    fake_tracker = MagicMock(spec=["count", "update"])
    fake_tracker.count = 0

    with patch("video_analyzer.build_trackers", return_value={"1": fake_tracker}), \
         patch("video_analyzer.PoseDetector") as MockDetector, \
         patch("video_analyzer.cv2.VideoCapture") as MockCapture:
        mock_detector = MockDetector.return_value
        mock_detector.detect.side_effect = [None, None]

        mock_cap = MockCapture.return_value
        mock_cap.read.side_effect = [(True, "frame1"), (True, "frame2"), (False, None)]

        result = analyze_video(str(tmp_path / "video.mp4"), "1")

    assert result == {"pose_detected": False, "final_value": 0}
    fake_tracker.update.assert_not_called()


def test_delete_video_file_removes_existing_file(tmp_path):
    path = tmp_path / "to_delete.mp4"
    path.write_text("fake video content")

    delete_video_file(str(path))

    assert not path.exists()


def test_delete_video_file_ignores_missing_file(tmp_path):
    path = str(tmp_path / "does_not_exist.mp4")
    delete_video_file(path)  # should not raise


def test_delete_video_file_ignores_none():
    delete_video_file(None)  # should not raise
