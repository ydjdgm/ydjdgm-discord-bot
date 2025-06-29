# ydjdgm Bot

**[🇰🇷 한국어](#-한국어) ∙ [🇺🇸 English](#-english)**

<br>

## 🇰🇷 한국어

Gemini AI와 연동하여 자연어 명령을 이해하는 스마트 음악봇입니다. 사용자는 일반적인 대화처럼 봇에게 재생, 스킵, 큐 관리 등을 요청할 수 있습니다.

## 🔧 명령어 목록

| 명령어                 | 설명                                                                                                                              | 사용법                                                     |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `/chat` | AI 챗봇과 대화하여 봇의 음악 기능을 자연어로 제어합니다.<br>*아직 업데이트 중* | `/chat message:[자연어 명령]` |
| `/play`                | 노래를 검색해 선택하거나, 유튜브 URL(영상/재생목록)을 큐에 추가합니다.<br>*재생목록 추가 시 `shuffle` 옵션으로 순서를 섞을 수 있습니다.* | `/play query:[유튜브 검색어 또는 URL] shuffle:[True/False]`        |
| `/playnext`            | 노래를 검색해 선택하거나, URL을 입력하여 바로 다음 곡으로 예약합니다.<br>*재생목록은 `/playnext`로 추가할 수 없습니다.*                 | `/playnext query:[유튜브 검색어 또는 URL]`                         |
| `/queue`               | 현재 재생 중인 노래와 대기열 목록을 보여주는 컨트롤러를 소환합니다.                                                                 | `/queue`                                                   |
| `/skip`                | 현재 재생 중인 노래를 건너뛰고 다음 곡을 재생합니다.                                                                              | `/skip`                                                    |
| `/pause`               | 현재 재생 중인 노래를 일시정지합니다.                                                                                             | `/pause`                                                   |
| `/resume`              | 일시정지된 노래를 다시 재생합니다.                                                                                                | `/resume`                                                  |
| `/stop`                | 음악 재생을 모두 멈추고 봇을 음성 채널에서 내보냅니다.                                                                            | `/stop`                                                    |
| `/nowplaying`          | 현재 재생 중인 노래의 상세 정보를 보여줍니다.                                                                                     | `/nowplaying`                                              |
| `/toggleautoleave`     | 큐가 비었을 때, 봇이 자동으로 음성 채널을 나가는 기능을 켜거나 끕니다.                                                             | `/toggleautoleave`                                         |
| `/togglealoneleave`    | 음성 채널에 봇 혼자 남았을 때, 자동으로 나가는 기능을 켜거나 끕니다.                                                                 | `/togglealoneleave`                                        |


### 🎵 UI 컨트롤러 설명

  * **검색 결과 선택 (`/play`, `/playnext`)**: 검색어 입력 시, 드롭다운 메뉴에서 원하는 곡을 직접 선택하여 재생목록에 추가할 수 있습니다.
  * **큐 컨트롤러 (`/queue`)**:
      * **🔀 랜덤**: 대기열의 순서를 무작위로 섞습니다.
      * **⏸️ 일시정지 / ▶️ 재생**: 현재 곡을 일시정지하거나 다시 재생합니다.
      * **⏭️ 스킵**: 현재 곡을 건너뜁니다.
      * **⏹️ 정지**: 음악 재생을 완전히 멈추고 봇이 채널을 나갑니다.
      * **\< 이전 / 다음 \>**: 대기열이 길 경우 페이지를 넘겨 확인합니다.
      * **삭제할 노래 선택... (드롭다운)**: 현재 페이지에 보이는 노래 중 특정 곡을 큐에서 제거합니다.
    
<br>

-----

<br>

## 🇺🇸 English

A smart music bot integrated with Gemini AI to understand natural language commands. Users can ask the bot to play, skip, manage the queue, and more, just like having a conversation.

### 🔧 Command List

| Command                | Description                                                                                                                     | Usage                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `/chat` | Chat with the AI to control all music features using natural language.<br>*still being updated* | `/chat message:[Your command]` |
| `/play`                | Searches for a song to select or adds a YouTube URL (video/playlist) to the queue.<br>*Use the `shuffle` option to shuffle playlists.* | `/play query:[YouTube keyword or URL] shuffle:[True/False]`         |
| `/playnext`            | Searches for a song to select or uses a URL to queue it up to play next.<br>*Playlists cannot be added with this command.*         | `/playnext query:[YouTube keyword or URL]`                          |
| `/queue`               | Summons a controller to view the currently playing song and the queue.                                                          | `/queue`                                                   |
| `/skip`                | Skips the currently playing song and plays the next one.                                                                        | `/skip`                                                    |
| `/pause`               | Pauses the currently playing song.                                                                                              | `/pause`                                                   |
| `/resume`              | Resumes playback of a paused song.                                                                                              | `/resume`                                                  |
| `/stop`                | Stops all music and disconnects the bot from the voice channel.                                                                 | `/stop`                                                    |
| `/nowplaying`          | Shows detailed information about the currently playing song.                                                                    | `/nowplaying`                                              |
| `/toggleautoleave`     | Toggles the feature to automatically leave the voice channel when the queue is empty.                                           | `/toggleautoleave`                                         |
| `/togglealoneleave`    | Toggles the feature to automatically leave when the bot is left alone in the voice channel.                                     | `/togglealoneleave`                                        |

### 🎵 UI Controller Guide

  * **Search Result Selector (`/play`, `/playnext`)**: When you search, you can select the exact song you want from a dropdown menu of results.
  * **Queue Controller (`/queue`)**:
      * **🔀 Shuffle**: Randomizes the order of songs in the queue.
      * **⏸️ Pause / ▶️ Resume**: Pauses or resumes the current song.
      * **⏭️ Skip**: Skips the current song.
      * **⏹️ Stop**: Stops playback entirely and makes the bot leave the channel.
      * **\< Prev / Next \>**: Navigates through pages of the queue if it's long.
      * **Select a song to remove... (Dropdown)**: Removes a specific song from the queue from the songs visible on the current page.
   
