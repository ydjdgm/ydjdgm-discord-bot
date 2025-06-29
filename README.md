# ydjdgm Bot

**[🇰🇷 한국어](#-한국어) ∙ [🇺🇸 English](#-english)**

<br>

## 🇰🇷 한국어

## 🔧 명령어 목록

| 명령어          | 설명                                                               | 사용법                                                     |
| -------------- | ------------------------------------------------------------------ | ---------------------------------------------------------- |
| `/play`        | 노래를 검색하거나 유튜브 URL(영상/재생목록)을 큐에 추가합니다.<br>재생목록 추가 시 shuffle 설정으로 노래의 순서를 섞어서 추가 할 수 있습니다.     | `/play query:[노래 제목, 키워드 또는 URL] shuffle:[True/False]` |
| `/playnext`    | 노래를 검색하거나 URL을 입력하여 바로 다음 곡으로 예약합니다.<br>(재생목록은 불가능)    | `/playnext query:[노래 제목, 키워드 또는 URL]`                 |
| `/queue`       | 현재 재생 중인 노래와 대기열 목록을 보여줍니다.                  | `/queue`                                                   |
| `/skip`        | 현재 재생 중인 노래를 건너뛰고 다음 곡을 재생합니다.             | `/skip`                                                    |
| `/pause`       | 현재 재생 중인 노래를 일시정지합니다.                            | `/pause`                                                   |
| `/resume`      | 일시정지된 노래를 다시 재생합니다.                               | `/resume`                                                  |
| `/stop`        | 모든 노래를 멈추고 봇을 음성 채널에서 내보냅니다.                | `/stop`                                                    |
| `/nowplaying`  | 현재 재생 중인 노래의 상세 정보를 보여줍니다.                    | `/nowplaying`                                              |

### 🎵 큐 컨트롤러 (버튼)

`/queue` 명령어를 사용하면 나타나는 UI입니다.

  - **🔀 랜덤**: 대기열의 순서를 무작위로 섞습니다.
  - **⏸️ 일시정지 / ▶️ 재생**: 현재 곡을 일시정지하거나 다시 재생합니다.
  - **⏭️ 스킵**: 현재 곡을 건너뜁니다.
  - **⏹️ 정지**: 음악 재생을 완전히 멈추고 봇이 채널을 나갑니다.
  - **\< 이전 / 다음 \>**: 대기열이 길 경우 페이지를 넘겨 확인합니다.
  - **삭제할 노래 선택... (드롭다운)**: 현재 페이지에 보이는 노래 중 특정 곡을 큐에서 제거합니다.
    
<br>

-----

<br>

## 🇺🇸 English

### 🔧 Command List

| Command        | Description                                                          | Usage                                                      |
| -------------- | -------------------------------------------------------------------- | ---------------------------------------------------------- |
| `/play`        | Searches for a song or adds a YouTube URL (video/playlist) to the queue.<br>When adding a playlist, you can shuffle the order of the songs with the shuffle parameter. | `/play query:[song title, keyword, or URL] shuffle:[True/False]` |
| `/playnext`    | Searches for a song or uses a URL to queue it up to play next.<br>(video only)       | `/playnext query:[song title, keyword, or URL]`                  |
| `/queue`       | Displays the currently playing song and the list of songs in the queue. | `/queue`                                                   |
| `/skip`        | Skips the currently playing song and plays the next one.             | `/skip`                                                    |
| `/pause`       | Pauses the currently playing song.                                   | `/pause`                                                   |
| `/resume`      | Resumes playback of a paused song.                                   | `/resume`                                                  |
| `/stop`        | Stops all music and disconnects the bot from the voice channel.      | `/stop`                                                    |
| `/nowplaying`  | Shows detailed information about the currently playing song.         | `/nowplaying`                                              |

### 🎵 Queue Controller (Buttons)

This UI appears when you use the `/queue` command.

  - **🔀 Shuffle**: Randomizes the order of songs in the queue.
  - **⏸️ Pause / ▶️ Resume**: Pauses or resumes the current song.
  - **⏭️ Skip**: Skips the current song.
  - **⏹️ Stop**: Stops playback entirely and makes the bot leave the channel.
  - **\< Prev / Next \>**: Navigates through pages of the queue if it's long.
  - **Select a song to remove... (Dropdown)**: Removes a specific song from the queue from the songs visible on the current page.
    
<br><br><br><br><br><br><br><br><br><br>

# update

- 사용자가 없으면 나가기 기능 (on/off command까지)
- queue에 노래 없을 때 나가기에 on/off command 달기
- /play, /playnext에 검색어 입력 시 검색결과 상위 5-10개 정도 표시하고 선택 가능하게
