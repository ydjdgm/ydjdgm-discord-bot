import discord
import yt_dlp
import asyncio
import random
import math
from discord.ui import View, Button
from config import TOKEN

# --- 설정 변수 ---
queue_ui_timeout = 180  # 큐 UI 타임아웃 (초)
bot_sleep_timeout = 60  # 봇 자동 퇴장 타임아웃 (초)
play_music_delete_timeout = 300  # '지금 재생 중' 메시지 자동 삭제 시간 (초)
YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True}
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
                search_query = query if query.startswith('http') else f"ytsearch:{query}"
                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    info = ydl.extract_info(search_query, download=False)

                    if 'entries' in info:
                        if not info['entries']:
                            return [], "❌ 해당 검색어로 노래를 찾을 수 없습니다."
                        info = info['entries'][0]
                    
                    song = {
                        'title': info.get('title'),
                        'uploader': info.get('uploader'),
                        'webpage_url': info.get('webpage_url'),
                        'channel_url': info.get('channel_url'),
                        'thumbnail': info.get('thumbnail'),
                        'requester': requester
                    }
                    return [song], f"✅ **{song['title']}** 을(를) 큐에 추가했습니다."

        songs_to_add, message = await loop.run_in_executor(None, extract)
        return songs_to_add, message

    # 음악을 직접적으로 재생하는 함수 (비동기)
    async def play_music(self):
        if not self.queue:
            self.current_song = None
            await asyncio.sleep(bot_sleep_timeout)
            voice_client = self.interaction.guild.voice_client
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
            if embed: await self.interaction.channel.send(embed=embed, delete_after=play_music_delete_timeout)

            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.play_next_song))
        except Exception as e:
            await self.interaction.channel.send(f"오류가 발생해 다음 곡을 재생합니다: {e}")
            await self.play_music()

    # 다음 곡 재생 (동기)
    def play_next_song(self):
        asyncio.run_coroutine_threadsafe(self.play_music(), self.bot.loop)

    # 재생 중인 곡 건너뛰기
    def skip(self):
        voice_client = self.interaction.guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop(); return True
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

    async def setup_hook(self):
        await self.tree.sync()
        print("명령어가 동기화되었습니다.")

    async def on_ready(self):
        print(f"{self.user}로 로그인했습니다.")

    def get_music_state(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        if guild_id not in self.music_states:
            self.music_states[guild_id] = GuildMusicState(self, interaction)
        self.music_states[guild_id].interaction = interaction
        return self.music_states[guild_id]

bot = MyBot()

# --- UI 클래스 ---
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
        self.total_pages = math.ceil(len(self.state.queue) / self.songs_per_page)
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
        await interaction.response.defer()
        if self.state.skip():
            await asyncio.sleep(0.5)
            self.update_view_data()
            embed = await self.create_embed()
            await interaction.edit_original_response(embed=embed, view=self)
        else: await interaction.followup.send("재생 중인 노래가 없습니다.", ephemeral=True)

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


# --- Commands ---
@bot.tree.command(name="play", description="노래나 재생목록 주소를 큐에 추가합니다.")
async def play(interaction: discord.Interaction, query: str, shuffle: bool = False):
    state = bot.get_music_state(interaction)
    if not interaction.user.voice:
        return await interaction.response.send_message("먼저 음성 채널에 참여해주세요!", ephemeral=True)

    await interaction.response.defer()

    async with state.lock:
        try:
            is_playlist = 'list=' in query and query.startswith('http')
            
            songs_to_add, message = await state._fetch_songs(query, interaction.user, is_playlist, shuffle)
            
            if not songs_to_add:
                return await interaction.followup.send(message)

            state.queue.extend(songs_to_add)
            await interaction.followup.send(message)

        except Exception as e:
            print(e)
            return await interaction.followup.send(f"오류가 발생했습니다: {e}")

        voice_client = interaction.guild.voice_client
        if not voice_client:
            voice_client = await interaction.user.voice.channel.connect()

        if not voice_client.is_playing():
            await state.play_music()

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

@bot.tree.command(name="playnext", description="노래를 바로 다음에 재생합니다.")
async def playnext(interaction: discord.Interaction, query: str):
    state = bot.get_music_state(interaction)
    if not interaction.user.voice:
        return await interaction.response.send_message("먼저 음성 채널에 참여해주세요!", ephemeral=True)
    
    # 재생목록은 playnext로 추가할 수 없도록 제한
    if 'list=' in query and query.startswith('http'):
        return await interaction.response.send_message("재생목록은 '바로 다음에 추가'할 수 없습니다. `/play` 명령어를 이용해주세요.", ephemeral=True)

    await interaction.response.defer()

    async with state.lock:
        try:
            # 재생목록이 아니므로 is_playlist=False
            songs_to_add, message = await state._fetch_songs(query, interaction.user, is_playlist=False)
            
            if not songs_to_add:
                return await interaction.followup.send("노래를 찾을 수 없습니다.")

            song_to_add = songs_to_add[0]
            state.queue.insert(0, song_to_add)
            
            await interaction.followup.send(f"✅ **{song_to_add['title']}** 을(를) 다음 곡으로 추가했습니다.")

        except Exception as e:
            return await interaction.followup.send(f"오류가 발생했습니다: {e}")

        voice_client = interaction.guild.voice_client
        if not voice_client:
            voice_client = await interaction.user.voice.channel.connect()

        if not voice_client.is_playing():
            await state.play_music()


if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("오류: config.py 파일에 디스코드 봇 토큰(TOKEN)이 설정되지 않았습니다.")
