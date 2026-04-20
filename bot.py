import discord
import json
import logging
import asyncio
import os
from discord import app_commands, ui
from typing import Optional, Dict, Any
from datetime import datetime

# Настройки
logging.basicConfig(level=logging.INFO)
TOKEN = "MTQ4NzM0MjAyOTgwNDQwNDgyNg.GfSEIN.lYjmE5omAY_JChWLoaJdtK3UF8S1bjsF6O32Dk" 
DATA_FILE = "manager_data.json"
OWNER_ID = 1305160929377521677

# --- МОДАЛЬНОЕ ОКНО РЕДАКТИРОВАНИЯ ---
class EditItemModal(ui.Modal, title='Редактирование элемента'):
    new_name = ui.TextInput(label='Название', min_length=1, max_length=50)
    new_desc = ui.TextInput(label='Описание', style=discord.TextStyle.paragraph, max_length=1000)

    def __init__(self, bot, channel_id, old_name):
        super().__init__()
        self.bot = bot
        self.channel_id = str(channel_id)
        self.old_name = old_name
        
        item = self.bot.data.get("titles", {}).get(self.channel_id, {}).get(old_name, {})
        self.new_name.default = old_name
        self.new_desc.default = item.get("description", "")

    async def on_submit(self, interaction: discord.Interaction):
        data = self.bot.data["titles"][self.channel_id]
        
        item_content = data.pop(self.old_name)
        item_content["description"] = self.new_desc.value
        data[self.new_name.value] = item_content
        
        await self.bot.save_data()
        await self.bot.update_manager(interaction.channel)
        await interaction.response.send_message("Данные обновлены.", ephemeral=True)


# --- ИНТЕРФЕЙС ---
class ManagerSelect(ui.Select):
    def __init__(self, channel_id: int, options_data: dict, placeholder: str):
        self.channel_id = channel_id
        self.options_data = options_data
        
        select_options = []
        if not options_data:
            select_options.append(discord.SelectOption(label="Пусто"))
        else:
            for name, data in options_data.items():
                select_options.append(discord.SelectOption(
                    label=name,
                    description=f"{data.get('description', '')[:50]}..."
                ))
        
        super().__init__(
            placeholder=placeholder,
            options=select_options,
            disabled=not options_data,
            custom_id=f"select_pro:{channel_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        data = self.options_data.get(val)
        
        if not data: 
            return await interaction.response.send_message("Ошибка: данные не найдены.", ephemeral=True)

        color_str = data.get("color", "2b2d31")
        try:
            color_val = int(color_str, 16) if color_str else 0x2b2d31
        except ValueError:
            color_val = 0x2b2d31

        embed = discord.Embed(
            title=val, 
            description=data.get('description', ''), 
            color=color_val
        )
        if data.get('image'): 
            embed.set_image(url=data['image'])
            
        # УСТАНАВЛИВАЕМ НОВЫЙ ТЕКСТ В ФУТЕР
        embed.set_footer(text="качайте")

        view = ui.View()
        
        if data.get('url'):
            view.add_item(ui.Button(label="Скачать", style=discord.ButtonStyle.link, url=data['url']))
        
        if data.get('password'):
            view.add_item(ui.Button(label=f"Пароль: {data['password']}", style=discord.ButtonStyle.gray, disabled=True))
        
        invited_users = interaction.client.data.get("invited", [])
        if interaction.user.guild_permissions.administrator or interaction.user.id in invited_users:
            btn = ui.Button(label="Изменить", style=discord.ButtonStyle.gray)
            btn.callback = lambda i: i.response.send_modal(EditItemModal(interaction.client, self.channel_id, val))
            view.add_item(btn)
            
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ManagerView(ui.View):
    def __init__(self, channel_id: int, options_data: dict, placeholder: str):
        super().__init__(timeout=None)
        self.add_item(ManagerSelect(channel_id, options_data, placeholder))


# --- ЯДРО БОТА ---
class ProBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.data: Dict[str, Any] = {"titles": {}, "settings": {}, "messages": {}, "invited": []}

    async def setup_hook(self):
        await self.load_data()
        for c_id, options in self.data.get("titles", {}).items():
            ph = self.data.get("settings", {}).get(c_id, {}).get("ph", "Выберите раздел...")
            self.add_view(ManagerView(int(c_id), options, ph))
        await self.tree.sync()
        self.loop.create_task(self.backup_loop())

    async def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                try:
                    loaded = json.load(f)
                    for key in self.data.keys():
                        if key in loaded:
                            self.data[key] = loaded[key]
                except json.JSONDecodeError:
                    print("Ошибка чтения файла данных.")

    async def save_data(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    async def backup_loop(self):
        while True:
            await asyncio.sleep(3600)
            with open(f"backup_{int(datetime.now().timestamp())}.json", "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)

    async def update_manager(self, channel: discord.TextChannel):
        c_id = str(channel.id)
        conf = self.data.get("settings", {}).get(c_id, {"t": "Менеджер", "d": "Используйте меню ниже", "ph": "Выберите раздел..."})
        options = self.data.get("titles", {}).get(c_id, {})
        
        embed = discord.Embed(title=conf.get('t', 'Менеджер'), description=conf.get('d', ''), color=0x5865f2)
        if conf.get("banner"): 
            embed.set_image(url=conf["banner"])

        view = ManagerView(channel.id, options, conf.get("ph", "Выберите раздел..."))
        m_id = self.data.get("messages", {}).get(c_id)
        
        try:
            if m_id:
                msg = await channel.fetch_message(int(m_id))
                await msg.edit(embed=embed, view=view)
                return
        except discord.NotFound:
            pass 

        new_msg = await channel.send(embed=embed, view=view)
        if "messages" not in self.data:
            self.data["messages"] = {}
        self.data["messages"][c_id] = new_msg.id
        await self.save_data()


bot = ProBot()

# --- КОМАНДЫ ---
@bot.tree.command(name="start", description="Запустить/обновить менеджер")
async def start(interaction: discord.Interaction):
    await bot.update_manager(interaction.channel)
    await interaction.response.send_message("Готово.", ephemeral=True)


@bot.tree.command(name="add_config", description="Настройка шапки")
async def add_config(
    interaction: discord.Interaction, channel: discord.TextChannel, 
    title: str, description: str, placeholder: str = "Выберите нужный раздел...",
    banner: Optional[discord.Attachment] = None):
    
    if not interaction.user.guild_permissions.administrator: 
        return await interaction.response.send_message("Нет прав.", ephemeral=True)
        
    bot.data["settings"][str(channel.id)] = {
        "t": title, "d": description.replace("\\n", "\n"), "ph": placeholder,
        "banner": banner.url if banner else None
    }
    await bot.save_data()
    await bot.update_manager(channel)
    await interaction.response.send_message("Конфигурация обновлена.", ephemeral=True)


@bot.tree.command(name="create_item", description="Добавить элемент")
async def create_item(
    interaction: discord.Interaction, channel: discord.TextChannel, 
    name: str, description: str, url: str, password: Optional[str] = None,
    color: str = "2b2d31", file: Optional[discord.Attachment] = None):
    
    invited_users = bot.data.get("invited", [])
    if not (interaction.user.guild_permissions.administrator or interaction.user.id in invited_users): 
        return await interaction.response.send_message("Нет прав.", ephemeral=True)
    
    c_id = str(channel.id)
    if "titles" not in bot.data: bot.data["titles"] = {}
    if c_id not in bot.data["titles"]: bot.data["titles"][c_id] = {}
    
    bot.data["titles"][c_id][name] = {
        "description": description.replace("\\n", "\n"), "url": url, 
        "image": file.url if file else None, "color": color.replace("#", ""), "password": password
    }
    await bot.save_data()
    await bot.update_manager(channel)
    await interaction.response.send_message(f"Добавлено: {name}", ephemeral=True)


@bot.tree.command(name="delete_item", description="Удалить элемент")
async def delete_item(interaction: discord.Interaction, channel: discord.TextChannel, name: str):
    if not interaction.user.guild_permissions.administrator: 
        return await interaction.response.send_message("Нет прав.", ephemeral=True)
        
    c_id = str(channel.id)
    if c_id in bot.data.get("titles", {}) and name in bot.data["titles"][c_id]:
        del bot.data["titles"][c_id][name]
        await bot.save_data()
        await bot.update_manager(channel)
        await interaction.response.send_message(f"Удалено: {name}", ephemeral=True)
    else:
        await interaction.response.send_message("Не найдено.", ephemeral=True)


@bot.event
async def on_ready(): 
    print(f"--- Бот {bot.user} готов ---")

bot.run(TOKEN)