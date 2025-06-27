import discord
import yt_dlp # 유튜브 영상 정보 추출
import asyncio
import random
import math
from discord.ui import View, Button
from config import TOKEN

queue_ui_timeout = 180
bot_sleep_timeout = 60
play_music_delete_timeout = 300

# YDL, FFMPEG 설정
YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True}
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
# 봇 권한 설정
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True



# /queue command의 UI에 쓸 View 클래스
class MusicControlView(View):
    def __init__(self, bot_instance, interaction):
        super().__init__(timeout=queue_ui_timeout)
        self.bot = bot_instance
        self.guild_id = interaction.guild.id
        self.interaction = interaction # 원본 interaction을 저장해 나중에 사용
        self.current_page = 0
        self.songs_per_page = 10
        self.update_view_data()

    # 뷰의 데이터를 최신 상태로 업데이트하는 헬퍼 함수
    def update_view_data(self):
        self.queue = self.bot.song_queues.get(self.guild_id, [])
        self.now_playing = self.bot.current_song.get(self.guild_id)
        self.total_pages = math.ceil(len(self.queue) / self.songs_per_page)
        self.update_buttons()
        # 드롭다운 메뉴도 최신 큐 상태로 업데이트
        self.update_remove_song_select()

    # 임베드를 생성하는 함수
    async def create_embed(self):
        embed = discord.Embed(title="🎶 음악 제어판", color=discord.Color.purple())
        if self.now_playing:
            title = self.now_playing.get('title', '알 수 없는 제목'); uploader = self.now_playing.get('uploader', '알 수 없는 채널')
            embed.add_field(name="▶️ 현재 재생 중", value=f"**{title}**\n`{uploader}`", inline=False)
        
        if not self.queue:
            if not self.now_playing: embed.description = "큐가 비어있습니다."
        else:
            start_index = self.current_page * self.songs_per_page; end_index = start_index + self.songs_per_page
            queue_list_str = ""
            for i, song in enumerate(self.queue[start_index:end_index], start=start_index + 1):
                title = song.get('title', '알 수 없는 제목'); uploader = song.get('uploader', '알 수 없는 채널')
                queue_list_str += f"`{i}`. {title[:30]}... - `{uploader}`\n"
            embed.add_field(name=f"📋 대기열 ({len(self.queue)}곡)", value=queue_list_str, inline=False)
            embed.set_footer(text=f"페이지 {self.current_page + 1}/{self.total_pages if self.total_pages > 0 else 1}")
        return embed

    # 버튼들의 활성화/비활성화 상태를 업데이트
    def update_buttons(self):
        # 페이지 버튼
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= self.total_pages - 1
        if self.total_pages <= 1:
            self.prev_page.disabled = True; self.next_page.disabled = True
        
        # 재생/일시정지 버튼 상태 업데이트
        voice_client = discord.utils.get(self.bot.voice_clients, guild=self.interaction.guild)
        if voice_client and voice_client.is_paused():
            self.pause_resume.label = "▶️ 재생"
        else:
            self.pause_resume.label = "⏸️ 일시정지"

    # 드롭다운 메뉴를 업데이트하는 함수
    def update_remove_song_select(self):
        # 기존 Select가 있다면 제거
        select_to_remove = next((child for child in self.children if isinstance(child, self.RemoveSongSelect)), None)
        if select_to_remove:
            self.remove_item(select_to_remove)
            
        # 새 Select 추가
        start_index = self.current_page * self.songs_per_page
        end_index = start_index + self.songs_per_page
        songs_on_page = self.queue[start_index:end_index]
        
        if songs_on_page:
            self.add_item(self.RemoveSongSelect(songs_on_page, start_index, self.bot))

    # --- 버튼 콜백들 ---
    @discord.ui.button(label="🔀 랜덤", style=discord.ButtonStyle.secondary, row=0)
    async def shuffle_queue(self, interaction: discord.Interaction, button: Button):
        if self.queue:
            random.shuffle(self.bot.song_queues[self.guild_id])
            self.update_view_data()
            embed = await self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("큐에 노래가 없습니다.", ephemeral=True)

    @discord.ui.button(label="⏯️ 일시정지", style=discord.ButtonStyle.secondary, row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: Button):
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice_client:
            if voice_client.is_playing():
                voice_client.pause(); button.label = "▶️ 재생"
            elif voice_client.is_paused():
                voice_client.resume(); button.label = "⏸️ 일시정지"
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True)

    @discord.ui.button(label="⏭️ 스킵", style=discord.ButtonStyle.primary, row=0)
    async def skip_song(self, interaction: discord.Interaction, button: Button):
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            # 노래가 바뀌면 뷰의 데이터가 달라지므로 잠시 후 뷰를 새로고침
            await asyncio.sleep(1) 
            self.update_view_data()
            embed = await self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("재생 중인 노래가 없습니다.", ephemeral=True)

    @discord.ui.button(label="⏹️ 정지", style=discord.ButtonStyle.danger, row=0)
    async def stop_player(self, interaction: discord.Interaction, button: Button):
        voice_client = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if voice_client:
            self.bot.song_queues[self.guild_id] = []
            self.bot.current_song.pop(self.guild_id, None)
            voice_client.stop()
            await voice_client.disconnect()
            await interaction.response.edit_message(content="⏹️ 재생을 멈추고 채널을 나갑니다.", embed=None, view=None)
        else:
            await interaction.response.send_message("봇이 음성 채널에 없습니다.", ephemeral=True)

    @discord.ui.button(label="< 이전", style=discord.ButtonStyle.blurple, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: Button):
        self.current_page -= 1; self.update_view_data()
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="다음 >", style=discord.ButtonStyle.blurple, row=1)
    async def next_page(self, interaction: discord.Interaction, button: Button):
        self.current_page += 1; self.update_view_data()
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    # --- 드롭다운 메뉴 클래스 (View 클래스 내에 정의) ---
    class RemoveSongSelect(discord.ui.Select):
        def __init__(self, songs, start_index, bot_instance):
            self.bot = bot_instance
            options = []
            for i, song in enumerate(songs):
                title = song.get('title', '알 수 없는 제목')
                # 옵션의 값(value)에 실제 큐의 인덱스를 저장하는 것이 핵심
                options.append(discord.SelectOption(label=f"{i+start_index+1}. {title[:80]}", value=str(i + start_index)))

            super().__init__(placeholder="삭제할 노래를 선택하세요...", min_values=1, max_values=1, options=options, row=2)

        async def callback(self, interaction: discord.Interaction):
            selected_index = int(self.values[0])
            guild_id = interaction.guild.id
            
            removed_song = self.bot.song_queues[guild_id].pop(selected_index)
            title = removed_song.get('title')
            
            # 뷰를 새로고침하여 변경사항을 즉시 반영
            view = MusicControlView(self.bot, interaction)
            embed = await view.create_embed()
            await interaction.response.edit_message(content=f"🗑️ '{title}'을(를) 큐에서 제거했습니다.", embed=embed, view=view)



# 봇 클래스 재정의
class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self) # commands tree
        self.song_queues = {} # 노래 queue
        self.current_song = {} # 현재 재생 중인 노래

    async def setup_hook(self):
        await self.tree.sync() # commands 동기화
        print("Commands are now synced.\n명령어가 동기화되었습니다.")

    async def on_ready(self): # 봇 시작 시
        print(f"Logged in as {self.user}.\n{self.user}로 로그인했습니다.")

    def play_next_song(self, interaction):
        guild_id = interaction.guild.id
        if guild_id in self.song_queues and self.song_queues[guild_id]:
            asyncio.run_coroutine_threadsafe(self.play_music(interaction), self.loop)
        else:
            self.current_song.pop(guild_id, None)

    async def play_music(self, interaction):
        guild_id = interaction.guild.id
        queue = self.song_queues.get(guild_id)

        if not queue:
            self.current_song.pop(guild_id, None)
            await asyncio.sleep(bot_sleep_timeout) # queue가 bot_sleep_timeout초 동안 비어있으면 disconnect
            voice_client = discord.utils.get(self.voice_clients, guild=interaction.guild)
            if voice_client and not voice_client.is_playing():
                await voice_client.disconnect()
            return
        
        song_info = queue.pop(0)
        self.current_song[guild_id] = song_info
        
        title = song_info['title']
        webpage_url = song_info['webpage_url']
        requester = song_info['requester']

        voice_client = discord.utils.get(self.voice_clients, guild=interaction.guild)
        if not voice_client: return

        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(webpage_url, download=False)
                stream_url = info['url']

            thumbnail_url = info.get('thumbnail')
            self.current_song[guild_id]['thumbnail'] = thumbnail_url

            embed = self._create_nowplaying_embed(song_info)
            await interaction.channel.send(embed=embed, delete_after=play_music_delete_timeout)

            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda _: self.play_next_song(interaction))
        except Exception as e:
            await interaction.channel.send(f"오류가 발생해 다음 곡을 재생합니다: {e}")
            self.play_next_song(interaction)

    def _create_nowplaying_embed(self, song_info):
        title = song_info.get('title', '알 수 없는 제목')
        webpage_url = song_info.get('webpage_url', '')
        uploader = song_info.get('uploader', '알 수 없는 채널')
        channel_url = song_info.get('channel_url', '')
        requester = song_info.get('requester')
        thumbnail_url = song_info.get('thumbnail')

        description_text = (
            f"[{title}]({webpage_url})\n\n"
            f"채널: [{uploader}]({channel_url})\n"
            f"신청자: {requester.mention}"
        )

        embed = discord.Embed(
            title="🎵 지금 재생 중",
            description=description_text,
            color=discord.Color.blue()
        )
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        
        return embed

bot = MyBot()



#########################################################################################################################################
#########################################################################################################################################
#########################################################################################################################################


@bot.tree.command(name="play", description="노래나 재생목록을 큐에 추가합니다.")
@discord.app_commands.describe(
    query="유튜브 url (단일영상/재생목록) 또는 검색어를 입력하세요.",
    shuffle="재생목록을 섞어서 추가할지 선택합니다. (기본값: False)"
)
async def play(interaction: discord.Interaction, query: str, shuffle: bool = False):
    if not interaction.user.voice:
        await interaction.response.send_message("먼저 음성 채널에 참여해주세요!", ephemeral=True)
        return
    
    await interaction.response.defer()

    guild_id = interaction.guild.id
    if guild_id not in bot.song_queues:
        bot.song_queues[guild_id] = []

    try:
        # --- yt-dlp 정보 추출 로직 ---
        songs_to_add = []
        
        # 재생목록 처리
        if 'list=' in query and 'https://' in query:
            with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True}) as ydl:
                playlist_dict = ydl.extract_info(query, download=False)
                if shuffle: random.shuffle(playlist_dict['entries'])
                for video in playlist_dict['entries']:
                    songs_to_add.append({ # 여기서 영상 정보 가져옴
                        'title': video.get('title', '알 수 없는 제목'),
                        'uploader': video.get('uploader', '알 수 없는 채널'),
                        'webpage_url': video.get('url'),
                        'channel_url': video.get('channel_url'),
                        'thumbnail': video.get('thumbnail'),
                        'requester': interaction.user
                    })
            await interaction.followup.send(f"✅ **{len(songs_to_add)}개**의 노래를 재생목록에서 가져와 큐에 추가했습니다.")
        
        # 단일 영상/검색어 처리
        else:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                if "https://" not in query:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
                else:
                    info = ydl.extract_info(query, download=False)
                
                song = { # 여기서 영상 정보 가져옴22
                    'title': info.get('title', '알 수 없는 제목'),
                    'uploader': info.get('uploader', '알 수 없는 채널'),
                    'webpage_url': info.get('webpage_url'),
                    'channel_url': info.get('channel_url'),
                    'thumbnail': info.get('thumbnail'),
                    'requester': interaction.user
                }
                songs_to_add.append(song)
                await interaction.followup.send(f"✅ **{song['title']}** 을(를) 큐에 추가했습니다.")
        
        # 추출된 노래들을 큐에 추가
        bot.song_queues[guild_id].extend(songs_to_add)

    except Exception as e:
        await interaction.followup.send(f"오류가 발생했습니다: {e}")
        return

    # 봇을 음성 채널에 연결하고 재생 시작
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not voice_client:
        await interaction.user.voice.channel.connect()
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
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
    view = MusicControlView(bot_instance=bot, interaction=interaction)
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



@bot.tree.command(name="playnext", description="노래를 바로 다음 곡으로 예약합니다.")
@discord.app_commands.describe(query="유튜브 url (단일영상) 또는 검색어를 입력하세요.")
async def playnext(interaction: discord.Interaction, query: str):
    if not interaction.user.voice:
        await interaction.response.send_message("먼저 음성 채널에 참여해주세요!", ephemeral=True)
        return
    
    await interaction.response.defer()

    guild_id = interaction.guild.id
    if guild_id not in bot.song_queues:
        bot.song_queues[guild_id] = []

    try:
        # /play 동일하게
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            if "https://" not in query:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
            else:
                info = ydl.extract_info(query, download=False)
            
            song = {
                'title': info.get('title', '알 수 없는 제목'),
                'uploader': info.get('uploader', '알 수 없는 채널'),
                'webpage_url': info.get('webpage_url'),
                'channel_url': info.get('channel_url'),
                'thumbnail': info.get('thumbnail'),
                'requester': interaction.user
            }

        # append 대신 insert로 큐 맨 앞에 노래를 추가
        bot.song_queues[guild_id].insert(0, song)
        
        await interaction.followup.send(f"↪️ **{song['title']}** 을(를) 다음 곡으로 예약했습니다.")

    except Exception as e:
        await interaction.followup.send(f"오류가 발생했습니다: {e}")
        return

    # 봇을 음성 채널에 연결하고 재생 시작
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if not voice_client:
        await interaction.user.voice.channel.connect()
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if not voice_client.is_playing():
        await bot.play_music(interaction)



@bot.tree.command(name="nowplaying", description="현재 재생 중인 노래 정보를 보여줍니다.") # 수리 필요
async def nowplaying(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    song_info = bot.current_song.get(guild_id)

    if not song_info:
        await interaction.response.send_message("현재 재생 중인 노래가 없습니다.", ephemeral=True)
        return
    
    embed = bot._create_nowplaying_embed(song_info)
    await interaction.response.send_message(embed=embed)



#########################################################################################################################################
#########################################################################################################################################
#########################################################################################################################################



if TOKEN:
    bot.run(TOKEN)
else:
    print("ERROR: 환경 변수 DISCORD_BOT_TOKEN이 설정되지 않았습니다.")