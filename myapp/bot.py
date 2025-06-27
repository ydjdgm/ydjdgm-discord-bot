import discord
import yt_dlp
import asyncio
import random
import math
from discord.ui import View, Button
from config import TOKEN





# yt-dlp 설정 (사운드만, 최고 음질): 단일 영상용
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}
# yt-dlp 옵션: 재생목록용
YDL_PLAYLIST_OPTIONS = {
    'format': 'bestaudio/best',
    'extract_flat': True,
    'quiet': True,
}

# FFmpeg 설정
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}




# --- 페이지네이션을 위한 View 클래스 ---
class QueueView(View):
    def __init__(self, queue, now_playing):
        super().__init__(timeout=180)  # 180초 동안 상호작용 없으면 버튼 비활성화
        self.queue = queue
        self.now_playing = now_playing
        self.current_page = 0
        self.songs_per_page = 10
        self.total_pages = math.ceil(len(self.queue) / self.songs_per_page)
        
        # 첫 페이지에서는 '이전' 버튼 비활성화
        self.prev_button.disabled = True
        # 페이지가 하나뿐이면 '다음' 버튼도 비활성화
        if self.total_pages <= 1:
            self.next_button.disabled = True

    async def create_embed(self):
        embed = discord.Embed(title="🎶 노래 큐", color=discord.Color.purple())
        
        # 1. 현재 재생 중인 곡 표시
        if self.now_playing:
            query = self.now_playing['query']
            # 너무 긴 URL은 잘라서 표시
            display_query = query if len(query) < 50 else query[:47] + "..."
            embed.add_field(
                name="▶️ 현재 재생 중", 
                value=f"**{display_query}**\n(신청자: {self.now_playing['requester'].mention})", 
                inline=False
            )
        
        # 2. 대기열 목록 표시 (페이지네이션)
        start_index = self.current_page * self.songs_per_page
        end_index = start_index + self.songs_per_page
        
        if not self.queue:
            embed.description = "대기열이 비어있습니다."
        else:
            queue_list_str = ""
            for i, song in enumerate(self.queue[start_index:end_index], start=start_index + 1):
                query = song['query']
                display_query = query if len(query) < 50 else query[:47] + "..."
                queue_list_str += f"`{i}`. {display_query}\n"
            
            embed.add_field(name="📋 대기열", value=queue_list_str, inline=False)
            embed.set_footer(text=f"페이지 {self.current_page + 1}/{self.total_pages}")
            
        return embed

    @discord.ui.button(label="< 이전", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: Button):
        self.current_page -= 1
        self.update_buttons()
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="다음 >", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: Button):
        self.current_page += 1
        self.update_buttons()
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= self.total_pages - 1




# 봇 권한 설정
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True


# 봇 클래스 재정의
class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self) # commands 트리
        self.song_queues = {} # 곡 리스트 (서버 단위로 저장)
        self.current_song = {} # 현재 재생 곡 정보

    async def setup_hook(self):
        await self.tree.sync()  # commands 동기화
        print("Commands are now synced.\n명령어가 동기화되었습니다.")

    async def on_ready(self): # 봇 시작시
        print(f"Logged in as {self.user}.\n{self.user}로 로그인했습니다.")

    # 노래가 끝나면 자동으로 다음 곡을 재생하는 함수
    def play_next_song(self, interaction):
        guild_id = interaction.guild.id
        if guild_id in self.song_queues and self.song_queues[guild_id]:
            # 다음 곡 재생을 위해 play_music 코루틴을 이벤트 루프에서 실행
            # asyncio.run_coroutine_threadsafe를 사용해 스레드 세이프하게 호출
            asyncio.run_coroutine_threadsafe(self.play_music(interaction), self.loop)

    # 음악을 실제로 재생하는 함수
    async def play_music(self, interaction):
        guild_id = interaction.guild.id
        queue = self.song_queues.get(guild_id)

        if not queue:
            self.current_song.pop(guild_id, None)
            await asyncio.sleep(60) # 큐가 비어있으면 60초 후 음성 채널에서 나감
            voice_client = discord.utils.get(self.voice_clients, guild=interaction.guild)
            if voice_client and not voice_client.is_playing():
                 await voice_client.disconnect()
            return
        
        # 큐에서 다음 곡을 꺼내오고 '현재 재생 곡'으로 설정
        song_info = queue.pop(0)
        self.current_song[guild_id] = song_info
        query = song_info['query']
        requester = song_info['requester']

        voice_client = discord.utils.get(self.voice_clients, guild=interaction.guild)
        if not voice_client:
            # 혹시 모를 상황에 대비해 음성 클라이언트가 없으면 다시 연결
            if interaction.user.voice:
                voice_client = await interaction.user.voice.channel.connect()
            else:
                await interaction.followup.send("ERROR: 음성 채널에 연결할 수 없습니다.")
                return
            
        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                if "https://" not in query:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
                else:
                    info = ydl.extract_info(query, download=False)
            
            url = info['url']
            title = info.get('title', '알 수 없는 제목')

            # '지금 재생 중' 메시지 전송
            embed = discord.Embed(title="🎵 지금 재생 중", description=f"**{title}**", color=discord.Color.blue())
            embed.add_field(name="신청자", value=requester.mention, inline=True)
            await interaction.channel.send(embed=embed, delete_after=300) # 5분 뒤 자동 삭제

            source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            # after 콜백: 노래가 끝나면 play_next_song 함수를 호출
            voice_client.play(source, after=lambda _: self.play_next_song(interaction))

        except Exception as e:
            await interaction.channel.send(f"오류가 발생해 다음 곡을 재생합니다: {e}")
            self.play_next_song(interaction)


# 봇 객체 생성
bot = MyBot()   





###################################################################################################################################
###################################################################################################################################
# COMMANDS



@bot.tree.command(name="hello", description="Say hello to the bot!")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello, {interaction.user.name}!")



@bot.tree.command(name="play", description="노래나 재생목록을 큐에 추가합니다.")
@discord.app_commands.describe(
    query="유튜브 url(영상/재생목록) 또는 검색어를 입력하세요.\n검색어 입력시 해당 검색어의 첫 번째 검색결과 영상이 재생됩니다", # 여기 UI 확인 필요
    shuffle="재생목록을 섞어서 추가할지 선택합니다. (기본값: False)"
)
async def play(interaction: discord.Interaction, query: str, shuffle: bool = False):
    if not interaction.user.voice:
        await interaction.response.send_message("먼저 음성 채널에 참여해주세요!", ephemeral=True)
        return
    
    await interaction.response.defer() # 로딩중 표시

    guild_id = interaction.guild.id
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    # 봇이 음성 채널에 없으면 연결
    if not voice_client:
        voice_client = await interaction.user.voice.channel.connect()

    # 큐가 없으면 새로 생성
    if guild_id not in bot.song_queues:
        bot.song_queues[guild_id] = []
    
    # --- 재생목록 처리 로직 ---
    is_playlist = 'list=' in query and 'https://' in query

    if is_playlist:
        try:
            with yt_dlp.YoutubeDL(YDL_PLAYLIST_OPTIONS) as ydl:
                playlist_dict = ydl.extract_info(query, download=False)
                videos = playlist_dict.get('entries', [])
                
                if not videos:
                    await interaction.followup.send("재생목록에서 영상을 찾을 수 없습니다.")
                    return
                
                if shuffle:
                    random.shuffle(videos) # 리스트 섞기
                
                for video in videos:
                    video_url = video.get('url')
                    if video_url:
                        song_info = {'query': video_url, 'requester': interaction.user}
                        bot.song_queues[guild_id].append(song_info)

            shuffle_text = " (랜덤)" if shuffle else ""
            await interaction.followup.send(f"✅ **{len(videos)}개**의 노래를 재생목록에서 가져와 큐에 추가했습니다{shuffle_text}.")

        except Exception as e:
            await interaction.followup.send(f"재생목록을 가져오는 중 오류가 발생했습니다: {e}")
            return
    else:
        # --- 단일 영상 또는 검색어 처리 로직 (기존과 동일) ---
        song_info = {'query': query, 'requester': interaction.user}
        bot.song_queues[guild_id].append(song_info)
        await interaction.followup.send(f"✅ **{query}** 을(를) 큐에 추가했습니다.")

    # 현재 아무것도 재생 중이 아닐 때만 재생 시작
    if not voice_client.is_playing():
        await bot.play_music(interaction)



@bot.tree.command(name="queue", description="노래 큐 목록을 보여줍니다.")
async def queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    queue_list = bot.song_queues.get(guild_id, [])
    now_playing = bot.current_song.get(guild_id)

    if not queue_list and not now_playing:
        await interaction.response.send_message("큐가 비어있습니다.", ephemeral=True)
        return

    # View를 생성하고 첫 페이지의 임베드를 가져옴
    view = QueueView(queue=queue_list, now_playing=now_playing)
    embed = await view.create_embed()
    
    await interaction.response.send_message(embed=embed, view=view)



@bot.tree.command(name="skip", description="현재 노래를 건너뛰고 다음 노래를 재생합니다.")
async def skip(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_playing():
        voice_client.stop() # 노래를 멈추면 play_next_song 콜백이 자동으로 호출됨
        await interaction.response.send_message("⏭️ 노래를 건너뛰었습니다.")
    else:
        await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True)



@bot.tree.command(name="pause", description="현재 노래를 일시정지합니다.")
async def pause(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("⏸️ 일시정지했습니다.")
    else:
        await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True)



@bot.tree.command(name="resume", description="일시정지된 노래를 다시 재생합니다.")
async def resume(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("▶️ 다시 재생합니다.")
    else:
        await interaction.response.send_message("일시정지된 노래가 없습니다.", ephemeral=True)



@bot.tree.command(name="stop", description="모든 노래를 멈추고 봇을 음성 채널에서 내보냅니다.")
async def stop(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

    if voice_client and voice_client.is_connected():
        # 큐 비우기
        bot.song_queues[guild_id] = []
        # 재생 멈추기
        voice_client.stop()
        # 음성 채널 나가기
        await voice_client.disconnect()
        await interaction.response.send_message("⏹️ 재생을 멈추고 채널을 나갑니다.")
    else:
        await interaction.response.send_message("봇이 음성 채널에 없습니다.", ephemeral=True)



###################################################################################################################################
###################################################################################################################################





if TOKEN:
    bot.run(TOKEN)
else:
    print("ERROR: 환경 변수 DISCORD_BOT_TOKEN이 설정되지 않았습니다.")