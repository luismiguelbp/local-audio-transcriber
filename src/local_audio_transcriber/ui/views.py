"""Main application view containers."""

import customtkinter as ctk

from .theme import (
    ACTION_BUTTON_TEXT_COLOR,
    BORDER_COLOR,
    CARD_CORNER_RADIUS,
    CARD_FG_COLOR,
    HELPER_TEXT_SIZE,
    MUTED_TEXT_COLOR,
    PRIMARY_ACTION_HEIGHT,
    PRIMARY_BUTTON_FG_COLOR,
    PRIMARY_BUTTON_HOVER_COLOR,
    PRIMARY_TEXT_COLOR,
    SECONDARY_BUTTON_FG_COLOR,
    SECONDARY_BUTTON_HOVER_COLOR,
    SECONDARY_BUTTON_TEXT_COLOR,
    SECONDARY_TEXT_COLOR,
    SUBSECTION_HEADING_SIZE,
    DROP_ZONE_FG_COLOR,
    neutral_option_menu_style,
    secondary_button_style,
)


class FileUploadView(ctk.CTkFrame):
    """File upload mode UI."""

    def __init__(
        self,
        master,
        supported_extensions: tuple[str, ...],
        on_browse_files,
        on_clear_queue,
        on_start_transcription,
    ):
        super().__init__(master, fg_color="transparent")

        self.drop_zone = ctk.CTkFrame(
            self,
            height=120,
            fg_color=DROP_ZONE_FG_COLOR,
            border_width=1,
            border_color=BORDER_COLOR,
            corner_radius=CARD_CORNER_RADIUS,
        )
        self.drop_zone.pack(fill="x", padx=20, pady=10)
        self.drop_zone.pack_propagate(False)

        drop_label_frame = ctk.CTkFrame(self.drop_zone, fg_color="transparent")
        drop_label_frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            drop_label_frame,
            text="Drop audio files here",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack()
        ctk.CTkLabel(
            drop_label_frame,
            text="or click the button below",
            font=ctk.CTkFont(size=12),
            text_color=SECONDARY_TEXT_COLOR,
        ).pack(pady=(5, 0))

        ctk.CTkButton(
            self,
            text="+ Add Audio Files",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=PRIMARY_ACTION_HEIGHT,
            corner_radius=8,
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            command=on_browse_files,
        ).pack(pady=10)

        ctk.CTkLabel(
            self,
            text=f"Supported formats: {', '.join(supported_extensions)}",
            font=ctk.CTkFont(size=HELPER_TEXT_SIZE),
            text_color=MUTED_TEXT_COLOR,
        ).pack()

        ctk.CTkLabel(
            self,
            text="File Queue",
            font=ctk.CTkFont(size=SUBSECTION_HEADING_SIZE, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
            anchor="w",
        ).pack(fill="x", padx=20, pady=(20, 5))

        self.queue_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=CARD_FG_COLOR,
            scrollbar_button_color=SECONDARY_BUTTON_FG_COLOR,
            scrollbar_button_hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            border_width=1,
            border_color=BORDER_COLOR,
            corner_radius=CARD_CORNER_RADIUS,
        )
        self.queue_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        self.empty_state_frame = ctk.CTkFrame(
            self.queue_frame,
            fg_color=DROP_ZONE_FG_COLOR,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        ctk.CTkLabel(
            self.empty_state_frame,
            text="No files added yet",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
        ).pack(padx=20, pady=(16, 4))
        ctk.CTkLabel(
            self.empty_state_frame,
            text="Add audio files to start a transcription batch.",
            font=ctk.CTkFont(size=HELPER_TEXT_SIZE),
            text_color=MUTED_TEXT_COLOR,
        ).pack(padx=20, pady=(0, 16))
        self.show_empty_state()

        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=20, pady=(0, 20))

        self.clear_btn = ctk.CTkButton(
            action_frame,
            text="Clear All",
            width=100,
            **secondary_button_style(),
            command=on_clear_queue,
            state="disabled",
        )
        self.clear_btn.pack(side="right")

        self.transcribe_btn = ctk.CTkButton(
            action_frame,
            text="Start Transcription",
            width=180,
            height=PRIMARY_ACTION_HEIGHT,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            command=on_start_transcription,
            state="disabled",
        )
        self.transcribe_btn.pack(side="left")

    def show_empty_state(self):
        if not self.empty_state_frame.winfo_manager():
            self.empty_state_frame.pack(padx=12, pady=16, fill="x")

    def hide_empty_state(self):
        if self.empty_state_frame.winfo_manager():
            self.empty_state_frame.pack_forget()


class LiveRecordingView(ctk.CTkFrame):
    """Live recording mode UI."""

    def __init__(
        self,
        master,
        model_values: list[str],
        mode_values: list[str],
        mode_help_text: str,
        on_refresh_devices,
        on_model_selected,
        on_mode_selected,
        on_toggle_recording,
        on_cancel_recording,
        on_copy_transcript,
    ):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        device_frame = ctk.CTkFrame(
            self,
            fg_color=CARD_FG_COLOR,
            corner_radius=CARD_CORNER_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        device_frame.pack(fill="x", padx=20, pady=(5, 10))
        device_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            device_frame,
            text="Microphone",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 6))
        self.mic_menu = ctk.CTkOptionMenu(
            device_frame,
            values=["Loading..."],
            **neutral_option_menu_style(),
        )
        self.mic_menu.grid(row=0, column=1, sticky="ew", padx=(0, 15), pady=(15, 6))

        ctk.CTkLabel(
            device_frame,
            text="System audio",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=15, pady=6)
        self.system_menu = ctk.CTkOptionMenu(
            device_frame,
            values=["Loading..."],
            **neutral_option_menu_style(),
        )
        self.system_menu.grid(row=1, column=1, sticky="ew", padx=(0, 15), pady=6)

        ctk.CTkButton(
            device_frame,
            text="Refresh Devices",
            width=130,
            **secondary_button_style(),
            command=on_refresh_devices,
        ).grid(row=0, column=2, rowspan=2, sticky="ns", padx=(0, 15), pady=(15, 6))

        ctk.CTkLabel(
            device_frame,
            text="Model",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=15, pady=6)
        self.model_menu = ctk.CTkOptionMenu(
            device_frame,
            values=model_values,
            command=on_model_selected,
            **neutral_option_menu_style(),
        )
        self.model_menu.grid(row=2, column=1, sticky="ew", padx=(0, 15), pady=(6, 15))

        ctk.CTkLabel(
            device_frame,
            text="Mode",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(row=3, column=0, sticky="w", padx=15, pady=(0, 15))
        self.live_recording_mode_menu = ctk.CTkOptionMenu(
            device_frame,
            values=mode_values,
            command=on_mode_selected,
            **neutral_option_menu_style(),
        )
        self.live_recording_mode_menu.grid(row=3, column=1, sticky="ew", padx=(0, 15), pady=(0, 15))

        self.mode_help_label = ctk.CTkLabel(
            device_frame,
            text=mode_help_text,
            text_color=MUTED_TEXT_COLOR,
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=HELPER_TEXT_SIZE),
        )
        self.mode_help_label.grid(row=4, column=1, sticky="ew", padx=(0, 15), pady=(0, 12))

        meter_frame = ctk.CTkFrame(
            self,
            fg_color=CARD_FG_COLOR,
            corner_radius=CARD_CORNER_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
        )
        meter_frame.pack(fill="x", padx=20, pady=(0, 10))
        meter_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            meter_frame,
            text="Mic level",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(15, 8))
        self.mic_level_bar = ctk.CTkProgressBar(
            meter_frame,
            height=12,
            corner_radius=8,
            progress_color=PRIMARY_BUTTON_FG_COLOR,
        )
        self.mic_level_bar.grid(row=0, column=1, sticky="ew", padx=(0, 15), pady=(15, 8))
        self.mic_level_bar.set(0)

        ctk.CTkLabel(
            meter_frame,
            text="System level",
            text_color=SECONDARY_TEXT_COLOR,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=15, pady=(0, 15))
        self.system_level_bar = ctk.CTkProgressBar(
            meter_frame,
            height=12,
            corner_radius=8,
            progress_color=PRIMARY_BUTTON_FG_COLOR,
        )
        self.system_level_bar.grid(row=1, column=1, sticky="ew", padx=(0, 15), pady=(0, 15))
        self.system_level_bar.set(0)

        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.record_btn = ctk.CTkButton(
            control_frame,
            text="Start Recording",
            width=180,
            height=PRIMARY_ACTION_HEIGHT,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=PRIMARY_BUTTON_FG_COLOR,
            hover_color=PRIMARY_BUTTON_HOVER_COLOR,
            text_color=ACTION_BUTTON_TEXT_COLOR,
            command=on_toggle_recording,
        )
        self.record_btn.pack(side="left")
        self.cancel_record_btn = ctk.CTkButton(
            control_frame,
            text="Cancel",
            width=110,
            height=PRIMARY_ACTION_HEIGHT,
            corner_radius=8,
            font=ctk.CTkFont(size=14),
            fg_color=SECONDARY_BUTTON_FG_COLOR,
            hover_color=SECONDARY_BUTTON_HOVER_COLOR,
            text_color=SECONDARY_BUTTON_TEXT_COLOR,
            command=on_cancel_recording,
            state="disabled",
        )

        self.live_status_label = ctk.CTkLabel(
            control_frame,
            text="Select devices, then speak or play audio to test the meters.",
            font=ctk.CTkFont(size=11),
            text_color=MUTED_TEXT_COLOR,
            anchor="w",
            justify="left",
        )
        self.live_status_label.pack(side="left", fill="x", expand=True, padx=15)

        transcript_header = ctk.CTkFrame(self, fg_color="transparent")
        transcript_header.pack(fill="x", padx=20, pady=(10, 5))
        ctk.CTkLabel(
            transcript_header,
            text="Live Transcript",
            font=ctk.CTkFont(size=SUBSECTION_HEADING_SIZE, weight="bold"),
            text_color=PRIMARY_TEXT_COLOR,
            anchor="w",
        ).pack(side="left")
        ctk.CTkButton(
            transcript_header,
            text="Copy to Clipboard",
            width=150,
            **secondary_button_style(),
            command=on_copy_transcript,
        ).pack(side="right")

        self.transcript_box = ctk.CTkTextbox(
            self,
            height=220,
            wrap="word",
            corner_radius=CARD_CORNER_RADIUS,
            border_width=1,
            border_color=BORDER_COLOR,
            fg_color=CARD_FG_COLOR,
            text_color=PRIMARY_TEXT_COLOR,
        )
        self.transcript_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.transcript_box.insert("1.0", "Transcript will appear here while recording.\n")
        self.transcript_box.configure(state="disabled")

