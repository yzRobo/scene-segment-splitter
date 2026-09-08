"""
video_processor_gui.py - GUI-facing wrapper around the core VideoProcessor.

The detection/splitting logic lives entirely in process_videos.VideoProcessor
(a single engine shared by the CLI and the GUI). This subclass exists so the GUI
can keep importing `VideoProcessorGUI`; all reliability logic is inherited.

The base class already supports everything the GUI needs:
  * config-driven parameters (apply_config),
  * a progress_callback (message, percentage),
  * cancellation (cancel_processing / cancel_requested),
  * per-file try/finally temp cleanup.
"""

from process_videos import VideoProcessor


class VideoProcessorGUI(VideoProcessor):
    """Thin GUI adapter over the shared engine."""

    def __init__(self, input_folder: str, output_folder: str, config: dict = None):
        super().__init__(input_folder, output_folder, config=config)
