import discord
import yt_dlp
import asyncio
import random
import math
import google.generativeai as genai
from discord.ui import View, Button
from config import TOKEN, GEMINI_API_KEY


# --- 음악봇 ---

# --- 설정 변수 ---
queue_ui_timeout = 180  # 큐 UI 타임아웃 (초)
bot_sleep_timeout = 60  # 봇 자동 퇴장 타임아웃 (초)
YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True, 'cookiefile': './cookies.txt',}
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
intents = discord.Intents.default() # 봇 권한
intents.message_content = True
intents.voice_states = True

# --- 상태 관리 클래스 ---
class GuildMusicState:
    def __init__(self, bot_instance, interaction):
        self.bot = bot_instance
        self.interaction = interaction
        self.queue = [] # 현재 서버의 큐 정보 변수
        self.current_song = None # 현재 재생 중인 곡 정보 변수
        self.lock = asyncio.Lock() # 경합 조건 막는 Lock (명령어 여러 개가 동시에 막 올 때 에러 방지용)
        self.auto_leave_on_empty = True # queue가 비었을 때 자동퇴장 on/off
        self.auto_leave_when_alone = True # 사용자 없을 때 자동퇴장 on/off
        self.leave_timer_task = None # 자동 퇴장 타이머

    # 현재 재생 중인 음악 정보 embed 생성 함수
    def _create_nowplaying_embed(self):
        if not self.current_song: return None
        song_info = self.current_song
        title, webpage_url, uploader, channel_url, requester, thumbnail_url = (
            song_info.get('title', '알 수 없는 제목'), song_info.get('webpage_url', ''),
            song_info.get('uploader', '알 수 없는 채널'), song_info.get('channel_url', ''),
            song_info.get('requester'), song_info.get('thumbnail')
        )
        description_text = (f"[{title}]({webpage_url})\n\n"
                            f"채널: [{uploader}]({channel_url})\n"
                            f"신청자: {requester.mention}")
        embed = discord.Embed(title="🎵 지금 재생 중", description=description_text, color=discord.Color.blue())
        if thumbnail_url: embed.set_thumbnail(url=thumbnail_url)
        return embed

    # 영상 정보 return하는 함수
    async def _fetch_songs(self, query: str, requester, is_playlist: bool, shuffle: bool = False):
        loop = self.bot.loop
        
        def extract():
            # URL이면서 재생목록일 경우
            if is_playlist:
                playlist_options = YDL_OPTIONS.copy()
                playlist_options['extract_flat'] = 'in_playlist'
                with yt_dlp.YoutubeDL({'extract_flat': 'in_playlist', 'quiet': True}) as ydl:
                    playlist_dict = ydl.extract_info(query, download=False)
                    songs = []
                    for video in playlist_dict['entries']:
                        if video: # None인 경우 제외
                            songs.append({
                                'title': video.get('title', '알 수 없는 제목'),
                                'uploader': video.get('uploader', '알 수 없는 채널'),
                                'webpage_url': f"https://www.youtube.com/watch?v={video.get('id')}", # 원본 URL 사용
                                'channel_url': video.get('channel_url'),
                                'thumbnail': f"https://i.ytimg.com/vi/{video.get('id')}/hqdefault.jpg", # 썸네일 URL 구성
                                'requester': requester
                            })
                    if shuffle:
                        random.shuffle(songs)
                    return songs, f"✅ **{len(songs)}개**의 노래를 재생목록에서 가져와 큐에 추가했습니다."
            
            # URL이거나 검색어일 경우 (단일 곡)
            else:
                # URL이 아니면 검색어로 처리
                if query.startswith('http'):
                    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                        info = ydl.extract_info(query, download=False)
                        song = {
                            'title': info.get('title'),
                            'uploader': info.get('uploader'),
                            'webpage_url': info.get('webpage_url'),
                            'channel_url': info.get('channel_url'),
                            'thumbnail': info.get('thumbnail'),
                            'requester': requester
                        }
                        return [song], f"✅ **{song['title']}** 을(를) 큐에 추가했습니다."
                else:
                    with yt_dlp.YoutubeDL({'format': 'bestaudio/best', 'quiet': True, 'default_search': 'ytsearch5'}) as ydl:
                        info = ydl.extract_info(query, download=False)
                        
                        if not info.get('entries'):
                            return [], "❌ 해당 검색어로 노래를 찾을 수 없습니다."
                        
                        songs = []
                        for entry in info['entries']:
                            songs.append({
                                'title': entry.get('title'),
                                'uploader': entry.get('uploader'),
                                'webpage_url': entry.get('webpage_url'),
                                'channel_url': entry.get('channel_url'),
                                'thumbnail': entry.get('thumbnail'),
                                'requester': requester
                            })
                        # 검색 결과 목록과, 선택 UI를 띄우라는 메시지를 반환
                        return songs, "🔍 아래 목록에서 재생할 노래를 선택해주세요."

        songs_to_add, message = await loop.run_in_executor(None, extract)
        return songs_to_add, message

    # 음악을 직접적으로 재생하는 함수 (비동기)
    async def play_music(self):
        if not self.queue:
            self.current_song = None

            if self.auto_leave_on_empty:
                await asyncio.sleep(bot_sleep_timeout)
                voice_client = self.interaction.guild.voice_client

                # 큐가 비어있고, 재생 중도 아닐 때만 퇴장
                if voice_client and not voice_client.is_playing() and not self.queue:
                    await voice_client.disconnect()
            return


        self.current_song = self.queue.pop(0)
        webpage_url = self.current_song.get('webpage_url')
        voice_client = self.interaction.guild.voice_client
        if not voice_client: return

        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(webpage_url, download=False)
                stream_url = info.get('url')
                if not self.current_song.get('thumbnail'):
                    self.current_song['thumbnail'] = info.get('thumbnail')

            embed = self._create_nowplaying_embed()
            if embed: await self.interaction.channel.send(embed=embed)

            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.play_next_song))
        except Exception as e:
            await self.interaction.channel.send(f"오류가 발생해 다음 곡을 재생합니다: {e}")
            await self.play_music()

    # 다음 곡 재생 (동기)
    def play_next_song(self):
        asyncio.run_coroutine_threadsafe(self.play_music(), self.bot.loop)

    # 인덱스 목록으로 큐에서 여러 곡을 삭제하는 함수
    def remove_songs_by_indices(self, indices_to_remove: list[int]) -> tuple[list[str], list[int]]:
        removed_songs_titles = []
        failed_indices = []
        
        # 큐의 인덱스는 0부터 시작하므로, 사용자가 입력한 1기반 인덱스를 0기반으로 변환
        # 예: [1, 3] -> [0, 2]
        zero_based_indices = [int(i) - 1 for i in indices_to_remove]

        # 여러 항목을 삭제할 때 리스트 인덱스가 꼬이는 것을 방지하기 위해,
        # 인덱스를 역순으로 (큰 숫자부터) 정렬
        for index in sorted(zero_based_indices, reverse=True):
            # 인덱스가 큐 범위 내에 있는지 확인
            if 0 <= index < len(self.queue):
                removed_song = self.queue.pop(index)
                removed_songs_titles.append(removed_song.get('title', '알 수 없는 제목'))
            else:
                # 유효하지 않은 인덱스는 실패 목록에 추가 (1기반으로 다시 변환)
                failed_indices.append(index + 1)
        
        # 삭제된 노래 제목들은 다시 정방향으로 정렬해서 반환 (사용자 보기 편하게)
        return sorted(removed_songs_titles), sorted(failed_indices)

    # 재생 중인 곡 건너뛰기
    def skip(self):
        voice_client = self.interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            return True
        return False


    # 재생 중인 곡 일시정지
    def pause(self):
        voice_client = self.interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.pause(); return True
        return False

    # 일시정지 중인 곡 다시 재생
    def resume(self):
        voice_client = self.interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume(); return True
        return False

    # 재생 멈추고 봇 내보내내기
    async def stop(self):
        voice_client = self.interaction.guild.voice_client
        if voice_client:
            self.queue.clear(); self.current_song = None
            voice_client.stop()
            await voice_client.disconnect()
            return True
        return False

# --- 봇 클래스 ---
class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)
        self.music_states = {}
        self.chat_sessions = {} # 채널 별로 AI 채팅 구분

    # commands 동기화
    async def setup_hook(self):
        await self.tree.sync()
        print("명령어가 동기화되었습니다.")

    # 봇 시작 시
    async def on_ready(self):
        print(f"{self.user}로 로그인했습니다.")

    # 서버 단위 변수, 함수들 가져오기
    def get_music_state(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id not in self.music_states:
            self.music_states[guild_id] = GuildMusicState(self, interaction)
        self.music_states[guild_id].interaction = interaction
        return self.music_states[guild_id]
    
    # 채널에 봇 혼자일 시 자동 퇴장 타이머 시작
    async def start_leave_timer(self, guild: discord.Guild):
        await asyncio.sleep(bot_sleep_timeout)

        # 시간이 지난 후에도 여전히 봇이 음성 채널에 있는지, 채널에 혼자인지 재확인
        voice_client = guild.voice_client
        if voice_client and len(voice_client.channel.members) == 1:
            state = self.music_states.get(guild.id)
            if state:
                await state.stop() # stop 함수로 퇴장

    # 사용자의 음성 채널 상태 변경을 감지
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # 봇이 채널에 없으면 무시
        if not member.guild.voice_client:
            return

        # 봇 자신의 상태 변경은 무시
        if member == self.user:
            return

        voice_client = member.guild.voice_client
        channel = voice_client.channel
        state = self.music_states.get(member.guild.id)
        
        # auto_leave_when_alone == False면 무시
        if not state or not state.auto_leave_when_alone:
            return

        # 봇 제외 채널에 있는 사용자 수 확인
        real_users = [m for m in channel.members if not m.bot]

        # 봇 혼자 남았을 경우
        if len(real_users) == 0:
            # 타이머 시작
            if not state.leave_timer_task or state.leave_timer_task.done():
                state.leave_timer_task = asyncio.create_task(self.start_leave_timer(member.guild))
        
        # 다른 사용자가 있을 경우
        else:
            if state.leave_timer_task and not state.leave_timer_task.done():
                state.leave_timer_task.cancel()
                state.leave_timer_task = None

bot = MyBot()

# --- UI 클래스 ---

# --- 검색 결과 선택용 드롭다운 메뉴 ---
class SongSelect(discord.ui.Select):
    def __init__(self, bot, songs):
        self.bot = bot
        self.songs = songs
        
        # 드롭다운 메뉴에 표시될 옵션 설정
        options = [
            discord.SelectOption(
                label=f"{i+1}. {song.get('title', '알 수 없는 제목')[:80]}",
                description=f"{song.get('uploader', '알 수 없는 채널')[:90]}",
                value=str(i)
            ) for i, song in enumerate(songs)
        ]
        
        super().__init__(placeholder="재생할 노래를 선택하세요...", min_values=1, max_values=1, options=options)

    # 사용자가 드롭다운에서 항목을 선택했을 때 실행되는 콜백
    async def callback(self, interaction: discord.Interaction):
        selected_index = int(self.values[0])
        selected_song = self.songs[selected_index]
        
        state = self.bot.get_music_state(interaction)
        
        # View 비활성화 + "노래를 선택했습니다" 메시지 표시
        self.disabled = True
        self.placeholder = selected_song.get('title')[:100]
        await interaction.response.edit_message(view=self.view)

        # /playnext 처리를 위한 로직 (view에 play_next 속성이 있으면)
        play_next_flag = getattr(self.view, 'play_next', False)

        async with state.lock:
            if play_next_flag:
                state.queue.insert(0, selected_song)
                await interaction.followup.send(f"✅ **{selected_song['title']}** 을(를) 다음 곡으로 추가했습니다.")
            else:
                state.queue.append(selected_song)
                await interaction.followup.send(f"✅ **{selected_song['title']}** 을(를) 큐에 추가했습니다.")

            voice_client = interaction.guild.voice_client
            if not voice_client:
                voice_client = await interaction.user.voice.channel.connect()

            if not voice_client.is_playing():
                await state.play_music()


# --- 드롭다운 메뉴를 담을 View ---
class SongSearchView(discord.ui.View):
    def __init__(self, bot, songs, *, play_next=False):
        super().__init__()
        self.play_next = play_next # /playnext 명령어인지 구분하는 플래그
        self.add_item(SongSelect(bot, songs))



# --- /queue 용 ---
class MusicQueueView(View):
    def __init__(self, bot_instance, interaction):
        super().__init__(timeout=queue_ui_timeout)
        self.bot = bot_instance
        self.state = self.bot.get_music_state(interaction)
        self.interaction = interaction
        self.current_page = 0
        self.songs_per_page = 10
        self.update_view_data()

    def update_view_data(self):
        queue_length = len(self.state.queue)
        
        # 대기열이 비어있어도 total_pages가 최소 1이 되도록
        self.total_pages = math.ceil(queue_length / self.songs_per_page) if queue_length > 0 else 1
        
        # 현재 페이지가 총 페이지 수를 넘어가지 않도록 조정 (삭제 등으로 인해 페이지 수가 줄었을 경우)
        if self.current_page >= self.total_pages:
            self.current_page = self.total_pages - 1

        self.update_buttons()
        self.update_remove_song_select()

    async def create_embed(self):
        embed = discord.Embed(title="🎶 음악 큐", color=discord.Color.purple())
        if self.state.current_song:
            title = self.state.current_song.get('title', '알 수 없는 제목')
            uploader = self.state.current_song.get('uploader', '알 수 없는 채널')
            embed.add_field(name="▶️ 현재 재생 중", value=f"**{title}**\n`{uploader}`", inline=False)
        if not self.state.queue:
            if not self.state.current_song: embed.description = "큐가 비어있습니다."
        else:
            start_index = self.current_page * self.songs_per_page
            end_index = start_index + self.songs_per_page
            queue_list_str = ""
            for i, song in enumerate(self.state.queue[start_index:end_index], start=start_index + 1):
                title = song.get('title', '알 수 없는 제목')
                uploader = song.get('uploader', '알 수 없는 채널')
                queue_list_str += f"`{i}`. {title[:30]}... - `{uploader}`\n"
            embed.add_field(name=f"📋 대기열 ({len(self.state.queue)}곡)", value=queue_list_str, inline=False)
            embed.set_footer(text=f"페이지 {self.current_page + 1}/{self.total_pages if self.total_pages > 0 else 1}")
        return embed

    def update_buttons(self):
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= self.total_pages - 1
        if self.total_pages <= 1:
            self.prev_page.disabled = True
            self.next_page.disabled = True

        voice_client = self.interaction.guild.voice_client
        if voice_client and voice_client.is_paused():
            self.pause_resume.label = "▶️ 재생"
        else:
            self.pause_resume.label = "⏸️ 일시정지"

    def update_remove_song_select(self):
        select_to_remove = next((child for child in self.children if isinstance(child, self.RemoveSongSelect)), None)
        if select_to_remove: self.remove_item(select_to_remove)
        start_index = self.current_page * self.songs_per_page
        end_index = start_index + self.songs_per_page
        songs_on_page = self.state.queue[start_index:end_index]
        if songs_on_page: self.add_item(self.RemoveSongSelect(songs_on_page, start_index, self.bot))

    @discord.ui.button(label="🔀 랜덤", style=discord.ButtonStyle.secondary, row=0)
    async def shuffle_queue(self, interaction: discord.Interaction, button: Button):
        if self.state.queue:
            random.shuffle(self.state.queue)
            await self.update_and_respond(interaction)
        else: await interaction.response.send_message("큐에 노래가 없습니다.", ephemeral=True)

    @discord.ui.button(label="⏸️ 일시정지", style=discord.ButtonStyle.secondary, row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: Button):
        if self.state.current_song:
            if interaction.guild.voice_client.is_paused():
                self.state.resume()
            else:
                self.state.pause()
            self.update_buttons()
            await interaction.response.edit_message(view=self)
        else: await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True)

    @discord.ui.button(label="⏭️ 스킵", style=discord.ButtonStyle.primary, row=0)
    async def skip_song(self, interaction: discord.Interaction, button: Button):
        if self.state.skip():
            await interaction.response.defer()
            await asyncio.sleep(0.5)
            self.update_view_data()
            embed = await self.create_embed()
            await interaction.edit_original_response(embed=embed, view=self)
            await interaction.followup.send("⏭️ 노래를 건너뛰었습니다.") # 후속 응답
        else: await interaction.response.send_message("재생 중인 노래가 없습니다.")

    @discord.ui.button(label="⏹️ 정지", style=discord.ButtonStyle.danger, row=0)
    async def stop_player(self, interaction: discord.Interaction, button: Button):
        if await self.state.stop():
            await interaction.response.edit_message(content="⏹️ 재생을 멈추고 채널을 나갑니다.", embed=None, view=None)
        else: await interaction.response.send_message("봇이 음성 채널에 없습니다.", ephemeral=True)

    @discord.ui.button(label="< 이전", style=discord.ButtonStyle.blurple, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        self.current_page -= 1
        await self.update_and_respond(interaction)

    @discord.ui.button(label="다음 >", style=discord.ButtonStyle.blurple, row=1)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        self.current_page += 1
        await self.update_and_respond(interaction)

    async def update_and_respond(self, interaction):
        self.update_view_data()
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    class RemoveSongSelect(discord.ui.Select):
        def __init__(self, songs, start_index, bot_instance):
            self.bot = bot_instance
            options = [discord.SelectOption(label=f"{i+start_index+1}. {s.get('title', '')[:80]}", value=str(i + start_index)) for i, s in enumerate(songs)]
            super().__init__(placeholder="삭제할 노래를 선택하세요...", min_values=1, max_values=1, options=options, row=2)

        async def callback(self, interaction: discord.Interaction):
            state = self.bot.get_music_state(interaction)
            selected_index = int(self.values[0])
            removed_song = state.queue.pop(selected_index)
            title = removed_song.get('title')
            view = MusicQueueView(self.bot, interaction)
            embed = await view.create_embed()
            await interaction.response.edit_message(content=f"🗑️ '{title}'을(를) 큐에서 제거했습니다.", embed=embed, view=view)



# --- AI 챗봇 ---

# 페르소나 정의
CHATBOT_PERSONA = """
너는 이 디스코드 서버의 AI 도우미이자, 사용자들의 든든한 친구 'ydjdgm'이야.
항상 친절하고 명확한 반말로 대화하고, 이모지는 문장의 끝에 가끔 하나씩만 사용해줘.

**너의 행동 지침:**

1.  **언어 사용 원칙**: 사용자가 사용하는 언어로 답변하는 것이 최우선이야.
    * 사용자가 **한국어**로 질문하면, 기존처럼 친절하고 명확한 **반말**로 대답해줘.
    * 사용자가 **다른 언어**(영어, 일본어 등)로 질문하면, 해당 언어의 **친절한 톤**으로 자연스럽게 대답해줘.
    * 이모지는 문장의 끝에 가끔 하나씩만 사용해서 감정을 표현해줘.

2.  **기능 실행 우선**: 사용자의 요청이 아래 '네가 사용할 수 있는 도구' 목록에 있는 기능으로 해결될 수 있다면, 반드시 설명 대신 **함수를 호출해서 즉시 실행**해줘.

3.  **기능 설명**: 사용자가 봇의 특정 기능(예: "/play")에 대해 "어떻게 써?", "뭐하는 거야?" 라고 명확히 물어볼 때만, 아래 '너의 지식 베이스'를 참고해서 구체적으로 알려줘.

4.  **일상 대화**: 위 경우에 해당하지 않는 모든 대화에서는 사용자의 좋은 친구가 되어줘.

---
### **[ 네가 사용할 수 있는 도구 (Action) ]**

이것은 네가 직접 호출할 수 있는 함수 목록이야. 사용자의 요청 의도를 파악해서 알맞은 함수를 사용해.

**[1. 음악 재생]**
* `play_song`: 사용자가 "노래 틀어줘", "큐에 추가해줘" 등 일반적인 재생을 원할 때 사용.
    * (예시) "아이유 노래 틀어줘" -> `play_song(query="아이유 노래")` 호출
* `play_song_next`: 사용자가 "다음 곡으로", "먼저 듣고 싶어" 등 우선 재생을 원할 때 사용.
    * (예시) "이 노래 다음에 바로 틀어줘" -> `play_song_next(query="이 노래")` 호출

**[2. 큐 관리]**
* `show_queue`: 사용자가 "큐 보여줘", "대기열 목록" 등 큐 전체를 보고 싶어할 때 사용.
* `remove_songs_from_queue`: 사용자가 "2번 노래 빼줘", "1번, 5번 삭제해" 등 특정 노래를 큐에서 제거하길 원할 때 사용. **반드시 삭제할 번호를 숫자로 된 리스트에 담아 `indices` 파라미터로 전달**해야 해.
    * (예시) "큐에서 2번, 5번 노래 빼줘" -> `remove_songs_from_queue(indices=[2, 5])` 호출

**[3. 재생 제어]**
* `get_now_playing`: "지금 뭐 나와?", "이 노래 뭐야?" 등 현재 재생 중인 노래 정보가 궁금할 때 사용.
* `skip_current_song`: "스킵", "넘겨", "다음 곡" 등 현재 노래를 건너뛰고 싶어할 때 사용.

---
### **[ 너의 지식 베이스: 명령어 설명 (Knowledge) ]**

이것은 사용자가 슬래시 명령어 자체에 대해 물어볼 때 참고할 정보야.

* **/play `query` `shuffle`**: 유튜브에서 노래를 검색하거나 URL, 재생목록을 큐에 추가하는 가장 기본적인 명령어. 검색 시에는 상위 5개 결과를 보여주고 고를 수 있게 해. `shuffle` 옵션으로 재생목록을 섞을 수도 있어.
* **/playnext `query`**: `/play`와 비슷하지만, 노래를 큐 맨 뒤가 아닌 바로 다음 순서에 추가해줘.
* **/queue**: 현재 재생 곡과 대기열을 보여주는 컨트롤러를 소환해. 버튼으로 랜덤 재생, 일시정지/재생, 스킵, 정지, 페이지 넘기기, 특정 곡 삭제가 가능해.
* **/skip**: 현재 노래를 건너뛰어.
* **/nowplaying**: 현재 재생 중인 노래의 상세 정보를 보여줘.
* **/stop**: 재생을 모두 멈추고 큐를 비운 뒤, 음성 채널에서 나가.
* **/pause** & **/resume**: 노래를 일시정지하거나 다시 재생해.
* **/toggleautoleave**: 큐가 비었을 때 60초 후 자동으로 나갈지 말지 설정.
* **/togglealoneleave**: 채널에 혼자 남았을 때 60초 후 자동으로 나갈지 말지 설정.
"""

# AI가 사용할 함수들 정의
music_tools = [
    # /nowplaying 명령어에 해당하는 도구
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="get_now_playing", # 이 이름은 실제 함수 이름이 아니라 /chat 로직 내에서 해당 함수를 호출하기 위한 이름임
                description="현재 재생 중인 노래의 정보를 가져옵니다.",
            )
        ]
    ),
    # /skip 명령어에 해당하는 도구
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="skip_current_song",
                description="현재 재생 중인 노래를 건너뜁니다.",
            )
        ]
    ),
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="play_song",
                description="지정된 쿼리(노래 제목 또는 키워드)로 노래를 검색하고 재생 목록 맨 뒤에 추가합니다.",
                # AI가 이 함수를 호출할 때 어떤 정보를 넘겨줘야 하는지 정의
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "query": genai.protos.Schema(type=genai.protos.Type.STRING, description="검색할 노래 제목 또는 키워드 또는 url")
                    },
                    required=["query"]
                )
            )
        ]
    ),
    # /playnext 명령어에 해당하는 도구
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="play_song_next",
                description="지정된 쿼리로 노래를 검색하고 바로 다음 곡으로 재생되도록 큐 맨 앞에 추가합니다.",
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "query": genai.protos.Schema(type=genai.protos.Type.STRING, description="검색할 노래 제목 또는 키워드")
                    },
                    required=["query"]
                )
            )
        ]
    ),
    # /queue 명령어에 해당하는 도구
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="show_queue",
                description="현재 대기열(큐)에 있는 노래 목록을 보여줍니다.",
            )
        ]
    ),
    # 큐에서 곡을 삭제하는 도구(복수도 가능)
    genai.protos.Tool(
        function_declarations=[
            genai.protos.FunctionDeclaration(
                name="remove_songs_from_queue",
                description="대기열(큐)에서 지정된 번호의 노래를 하나 또는 여러 개 삭제합니다.",
                # AI가 이 함수를 호출할 때 어떤 정보를 넘겨줘야 하는지 정의합니다.
                parameters=genai.protos.Schema(
                    type=genai.protos.Type.OBJECT,
                    properties={
                        "indices": genai.protos.Schema(
                            type=genai.protos.Type.ARRAY, # 여러 값을 받기 위해 ARRAY 타입 사용
                            description="삭제할 노래의 대기열 번호 목록 (예: 2번, 5번을 삭제하려면 [2, 5] 전달)",
                            items=genai.protos.Schema(type=genai.protos.Type.INTEGER) # 배열의 각 항목은 숫자여야 함
                        )
                    },
                    required=["indices"]
                )
            )
        ]
    ),
            
    # (나중에 추가 예정)

]

# Gemini 모델 초기화
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    generation_config = {"temperature": 0.8, "top_p": 0.9}
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]
    
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        generation_config=generation_config,
        system_instruction=CHATBOT_PERSONA,
        safety_settings=safety_settings,
        tools=music_tools # 여기서 함수 정의한거 알려주는거임
    )

else:
    model = None



# --- Commands ---
@bot.tree.command(name="play", description="노래를 검색하거나 유튜브 주소를 큐에 추가합니다.")
async def play(interaction: discord.Interaction, query: str, shuffle: bool = False):
    state = bot.get_music_state(interaction)
    if not interaction.user.voice:
        return await interaction.response.send_message("먼저 음성 채널에 참여해주세요!", ephemeral=True)

    await interaction.response.defer()

    is_playlist = 'list=' in query and query.startswith('http')
    
    songs, message = await state._fetch_songs(query, interaction.user, is_playlist, shuffle)
    
    if not songs:
        return await interaction.followup.send(message)

    # 검색어가 아닌 URL, 재생목록의 경우 (즉시 추가)
    if query.startswith('http') or is_playlist:
        async with state.lock:
            state.queue.extend(songs)
            await interaction.followup.send(message)
            
            voice_client = interaction.guild.voice_client
            if not voice_client:
                voice_client = await interaction.user.voice.channel.connect()

            if not voice_client.is_playing():
                await state.play_music()
    # 검색어의 경우 (선택 UI 전송)
    else:
        view = SongSearchView(bot, songs)
        await interaction.followup.send(message, view=view)

@bot.tree.command(name="playnext", description="노래를 검색하여 바로 다음에 재생합니다.")
async def playnext(interaction: discord.Interaction, query: str):
    state = bot.get_music_state(interaction)
    if not interaction.user.voice:
        return await interaction.response.send_message("먼저 음성 채널에 참여해주세요!", ephemeral=True)
    
    if 'list=' in query and query.startswith('http'):
        return await interaction.response.send_message("재생목록은 '바로 다음에 추가'할 수 없습니다.", ephemeral=True)

    await interaction.response.defer()

    songs, message = await state._fetch_songs(query, interaction.user, is_playlist=False)

    if not songs:
        return await interaction.followup.send(message)

    # URL인 경우 (즉시 추가)
    if query.startswith('http'):
        async with state.lock:
            state.queue.insert(0, songs[0])
            await interaction.followup.send(message)
            
            voice_client = interaction.guild.voice_client
            if not voice_client:
                voice_client = await interaction.user.voice.channel.connect()

            if not voice_client.is_playing():
                await state.play_music()
    # 검색어인 경우 (선택 UI 전송)
    else:
        # play_next=True 플래그를 전달
        view = SongSearchView(bot, songs, play_next=True)
        await interaction.followup.send(message, view=view)

@bot.tree.command(name="queue", description="노래 큐 목록을 보여줍니다.")
async def queue(interaction: discord.Interaction):
    state = bot.get_music_state(interaction)
    if not state.queue and not state.current_song:
        return await interaction.response.send_message("큐가 비어있습니다.", ephemeral=True)
    view = MusicQueueView(bot_instance=bot, interaction=interaction)
    embed = await view.create_embed()
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="skip", description="현재 노래를 건너뛰고 다음 노래를 재생합니다.")
async def skip(interaction: discord.Interaction):
    state = bot.get_music_state(interaction)
    if state.skip(): await interaction.response.send_message("⏭️ 노래를 건너뛰었습니다.")
    else: await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True)

@bot.tree.command(name="pause", description="현재 노래를 일시정지합니다.")
async def pause(interaction: discord.Interaction):
    state = bot.get_music_state(interaction)
    if state.pause(): await interaction.response.send_message("⏸️ 일시정지했습니다.")
    else: await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True)

@bot.tree.command(name="resume", description="일시정지된 노래를 다시 재생합니다.")
async def resume(interaction: discord.Interaction):
    state = bot.get_music_state(interaction)
    if state.resume(): await interaction.response.send_message("▶️ 다시 재생합니다.")
    else: await interaction.response.send_message("일시정지된 노래가 없습니다.", ephemeral=True)

@bot.tree.command(name="stop", description="모든 노래를 멈추고 봇을 음성 채널에서 내보냅니다.")
async def stop(interaction: discord.Interaction):
    state = bot.get_music_state(interaction)
    if await state.stop():
        await interaction.response.send_message("⏹️ 재생을 멈추고 채널을 나갑니다.")
    else: await interaction.response.send_message("봇이 음성 채널에 없습니다.", ephemeral=True)

@bot.tree.command(name="nowplaying", description="현재 재생 중인 노래 정보를 보여줍니다.")
async def nowplaying(interaction: discord.Interaction):
    state = bot.get_music_state(interaction)
    if not state.current_song:
        return await interaction.response.send_message("현재 재생 중인 노래가 없습니다.", ephemeral=True)

    embed = state._create_nowplaying_embed()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="toggleautoleave", description="큐가 비었을 때 봇이 자동으로 나가는 기능을 켜거나 끕니다.")
async def toggleautoleave(interaction: discord.Interaction):
    state = bot.get_music_state(interaction)

    state.auto_leave_on_empty = not state.auto_leave_on_empty

    if state.auto_leave_on_empty:
        await interaction.response.send_message("✅ 이제부터 큐가 비면 봇이 자동으로 채널을 나갑니다.")
    else:
        await interaction.response.send_message("❌ 이제부터 큐가 비어도 봇이 자동으로 나가지 않습니다.")

@bot.tree.command(name="togglealoneleave", description="음성 채널에 봇 혼자 있을 때 자동으로 나가는 기능을 켜거나 끕니다.")
async def togglealoneleave(interaction: discord.Interaction):
    state = bot.get_music_state(interaction)

    state.auto_leave_when_alone = not state.auto_leave_when_alone

    if state.auto_leave_when_alone:
        await interaction.response.send_message("✅ 이제 음성 채널에 혼자 남으면 봇이 자동으로 나갑니다.")
    else:
        await interaction.response.send_message("❌ 이제 음성 채널에 혼자 남아도 봇이 자동으로 나가지 않습니다.")

@bot.tree.command(name="chat", description="AI 챗봇과 대화하고, 명령을 내립니다.")
async def chat(interaction: discord.Interaction, message: str):
    if not model:
        await interaction.response.send_message("챗봇 모델이 아직 설정되지 않았습니다.", ephemeral=True)
        return
        
    await interaction.response.defer()

    channel_id = interaction.channel.id
    
    if channel_id not in bot.chat_sessions:
        bot.chat_sessions[channel_id] = model.start_chat(history=[])
    chat_session = bot.chat_sessions[channel_id]

    try:
        # --- 1. AI 응답에 타임아웃 설정 ---
        try:
            # AI의 응답을 최대 20초까지 기다림
            response = await asyncio.wait_for(chat_session.send_message_async(message), timeout=20.0)
        except asyncio.TimeoutError:
            # 20초가 지나면 타임아웃 에러를 발생시키고 사용자에게 알림
            await interaction.followup.send("🤔 AI가 생각하는 데 시간이 너무 오래 걸리네. 다시 시도해 줄래?", ephemeral=True)
            return

        function_call = None
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    function_call = part.function_call
                    break

        if function_call:
            tool_name = function_call.name
            state = bot.get_music_state(interaction) # state를 미리 가져옴

            # --- 노래 재생/추가 관련 기능 ---
            if tool_name in ["play_song", "play_song_next"]:
                if not interaction.user.voice:
                    await interaction.followup.send("노래를 틀려면 먼저 음성 채널에 들어가야 해.", ephemeral=True)
                    return
                
                query = function_call.args.get("query")
                if not query:
                    await interaction.followup.send("무슨 노래를 틀어야 할지 모르겠어. 노래 제목을 알려줄래?", ephemeral=True)
                    return

                # --- 2. 유튜브 검색(yt-dlp)에 타임아웃 설정 ---
                try:
                    # 노래 검색을 최대 20초까지 기다림
                    songs, fetch_message = await asyncio.wait_for(state._fetch_songs(query, interaction.user, is_playlist=False), timeout=20.0)
                except asyncio.TimeoutError:
                    await interaction.followup.send("유튜브에서 노래를 찾는데 너무 오래 걸려서 취소했어. 다른 키워드로 시도해볼래?", ephemeral=True)
                    return

                if not songs:
                    await interaction.followup.send(f"'{query}'(으)로 노래를 찾지 못했어. 다른 키워드로 다시 말해줄래?", ephemeral=True)
                    return

                song_to_play = songs[0]

                async with state.lock:
                    if tool_name == "play_song_next":
                        state.queue.insert(0, song_to_play)
                        confirm_message = f"✅ 알겠어! **{song_to_play['title']}** 을(를) 다음 곡으로 추가할게."
                    else: # play_song
                        state.queue.append(song_to_play)
                        confirm_message = f"✅ 알겠어! **{song_to_play['title']}** 을(를) 큐에 추가할게."

                    voice_client = interaction.guild.voice_client
                    if not voice_client:
                        voice_client = await interaction.user.voice.channel.connect()
                    
                    if not voice_client.is_playing():
                        await state.play_music()
                
                await interaction.followup.send(confirm_message)
                return

            # --- 기타 다른 기능들 ---
            elif tool_name == "skip_current_song":
                if state.skip():
                    await interaction.followup.send("⏭️ 노래를 건너뛰었습니다.")
                else:
                    await interaction.followup.send("재생 중인 노래가 없습니다.", ephemeral=True)
                return
            
            elif tool_name == "get_now_playing":
                if state.current_song:
                    embed = state._create_nowplaying_embed()
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("현재 재생 중인 노래가 없습니다.", ephemeral=True)
                return
            # --- '/queue' 보기 기능 실행 ---
            elif tool_name == "show_queue":
                if not state.queue and not state.current_song:
                    await interaction.followup.send("큐가 비어있어. 보여줄 게 없네!")
                    return

                # 기존 /queue처럼 View와 Embed를 생성해서 보여줌
                view = MusicQueueView(bot_instance=bot, interaction=interaction)
                embed = await view.create_embed()
                await interaction.followup.send(embed=embed, view=view)
                return

            # --- 큐에서 노래 삭제 기능 실행 ---
            elif tool_name == "remove_songs_from_queue":
                indices = function_call.args.get("indices")
                if not indices:
                    await interaction.followup.send("몇 번 노래를 삭제해야 할지 알려주지 않았어.", ephemeral=True)
                    return

                # GuildMusicState에 만든 함수를 호출해 삭제 작업
                removed_titles, failed_indices = state.remove_songs_by_indices(indices)
                
                # 결과에 따라 사용자에게 보낼 메시지를 만듬
                response_parts = []
                if removed_titles:
                    # 삭제 성공한 노래 목록
                    response_parts.append(f"🗑️ **{len(removed_titles)}개**의 노래를 큐에서 삭제했어: `{'`, `'.join(removed_titles)}`")
                if failed_indices:
                    # 실패한 인덱스 목록
                    response_parts.append(f"🤔 요청한 번호 중 **{failed_indices}**번은 큐에 없거나 잘못된 번호라 삭제하지 못했어.")
                
                final_response = "\n".join(response_parts)
                await interaction.followup.send(final_response)
                return
            
            else:
                 await interaction.followup.send(f"🤔 '{tool_name}'이라는 기능은 아직 없어. 내가 할 수 있는 다른 일이 있을까?", ephemeral=True)
        
        else: # 함수 호출이 아닌 일반 답변
            embed = discord.Embed(
                color=discord.Color.gold(),
                description=message
                # description=response.text
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
            # embed.add_field(name="질문 내용", value=f"> {message}", inline=False)
            embed.add_field(name="", value=f"> {response.text}", inline=False)
            await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f"Chatbot command error: {e}")
        await interaction.followup.send("🤯 으악! 지금 머리가 너무 복잡해서 생각할 수가 없어. 조금만 있다가 다시 말 걸어줘!", ephemeral=True)

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("오류: 디스코드 봇 토큰(TOKEN)이 설정되지 않았습니다.")
