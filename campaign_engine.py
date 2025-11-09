from platform_loader import PC, display, buttonA, buttonB, buttonU, buttonD, buttonL, buttonR, dpadPressed, inputJustPressed, IS_THUMBY_COLOR
from time import sleep
from utime import ticks_ms, ticks_diff
import json
import os
from machine import freq
from gc import collect
import micropython
try:
    from micropython import const
except ImportError:
    def const(x):
        return x

# Constants
MAX_TEXT_WIDTH = const(70)
TEXT_SCROLL_DELAY = const(40)  # ms between text scroll steps

class CampaignEngine:
    def __init__(self, game_loc="/Games/ThumbCommander/"):
        self.game_loc = game_loc
        self.campaign_data = None
        self.current_campaign = None
        self.current_mission = 0
        self.total_score = 0
        self.campaign_saves = {}
        self.campaign_order = []
        self.load_campaigns()
        self.background = None
        display.setFont("/lib/font3x5.bin", 3, 5, 1)

    def load_campaigns(self):
        """Load all available campaign files from the game directory"""
        try:
            # Get list of campaign files
            campaign_files = [f for f in os.listdir(self.game_loc) if f.endswith("_campaign.json")]
            campaign_files.sort()
            self.campaigns = {}
            self.campaign_order = []
            
            for file in campaign_files:
                try:
                    with open(self.game_loc + file, 'r') as f:
                        campaign_data = json.loads(f.read())
                        campaign_title = campaign_data["title"]
                        self.campaigns[campaign_title] = {
                            "file": file,
                            "description": campaign_data.get("description", "No description")
                        }
                        self.campaign_order.append(campaign_title)
                except (OSError, ValueError, KeyError) as e:
                    # Skip invalid campaign files
                    print(f"Error loading {file}: {e}")
            
            # Load saved games
            try:
                with open(self.game_loc + "campaign_saves.json", 'r') as f:
                    self.campaign_saves = json.loads(f.read())
            except (OSError, ValueError):
                # No saves yet or corrupted file
                self.campaign_saves = {}
        except OSError:
            # No campaigns found
            self.campaigns = {}
            self.campaign_order = []

    def load_campaign(self, campaign_file):
        """Load a specific campaign file"""
        try:
            with open(self.game_loc + campaign_file, 'r') as f:
                self.campaign_data = json.loads(f.read())
                self.current_campaign = self.campaign_data["title"]
                return True
        except (OSError, ValueError, KeyError) as e:
            print(f"Error loading campaign: {e}")
            return False

    def save_progress(self):
        """Save current campaign progress"""
        if not self.current_campaign:
            return False
            
        self.campaign_saves[self.current_campaign] = {
            "mission": self.current_mission,
            "score": self.total_score
        }
        
        try:
            with open(self.game_loc + "campaign_saves.json", 'w') as f:
                f.write(json.dumps(self.campaign_saves))
            return True
        except OSError:
            return False

    def load_progress(self, campaign_title):
        """Load saved progress for a campaign"""
        if campaign_title in self.campaign_saves:
            save_data = self.campaign_saves[campaign_title]
            self.current_mission = save_data["mission"]
            self.total_score = save_data["score"]
            return True
        return False

    def select_campaign_menu(self):
        """Show menu to select a campaign"""
        if not self.campaigns:
            self.show_message("No campaigns available", "Please add campaign files to the game directory")
            return None
            
        campaigns = self.campaign_order
        selected = 0
        
        # Platform-specific spacing and positioning
        if IS_THUMBY_COLOR:
            # ThumbyColor with 8x8 font needs more spacing
            campaign_spacing = 30  # More space between campaigns
            header_y = 19
            line_y = 33
            first_campaign_y = 40
            back_button_y = PC.HEIGHT - PC.FONT_HEIGHT - 15  # Higher positioning
            tag_margin = 4
            line_spacing = PC.FONT_HEIGHT + 2  # Space between lines in multi-line names
            text_offset_x = 4
        else:
            # Original Thumby with 3x5 font
            campaign_spacing = 30
            header_y = 4
            line_y = 18
            first_campaign_y = 24
            back_button_y = PC.HEIGHT - PC.FONT_HEIGHT - 2
            tag_margin = 2
            line_spacing = PC.FONT_HEIGHT
            text_offset_x = 0
        
        while True:
            display.fill(0)
            if self.background:
                self.background.run(0)
                
            # Draw header - use font width for centering
            header_text = "SELECT CAMPAIGN"
            header_x = (PC.WIDTH - len(header_text) * PC.FONT_WIDTH) // 2
            display.drawText(header_text, header_x, header_y, PC.WHITE)
            display.drawLine(0, line_y, PC.WIDTH, line_y, PC.WHITE)
            
            # Calculate which campaigns to show (only show 2 at a time)
            start_idx = max(0, selected - (0 if selected == 0 else 1))
            
            # Draw campaigns - only show 2 at a time with platform-appropriate spacing
            for i in range(start_idx, min(start_idx + 2, len(campaigns))):
                campaign_y = first_campaign_y + (i - start_idx) * campaign_spacing
                text_color = PC.WHITE if i == selected else PC.LIGHTGRAY
                
                # Display campaign name with word wrapping
                campaign_name = campaigns[i]
                
                # Calculate max chars per line based on font width (leave space for tag)
                tag_text = "CON" if campaigns[i] in self.campaign_saves else "NEW"
                tag_width = len(tag_text) * PC.FONT_WIDTH + tag_margin * 2
                available_width = PC.WIDTH - 8 - tag_width  # Left margin + tag space
                max_chars = available_width // PC.FONT_WIDTH
                
                # Tag positioning
                tag_x = PC.WIDTH - tag_width
                
                # If campaign name fits on one line
                if len(campaign_name) * PC.FONT_WIDTH <= available_width:
                    # Single line display - center vertically in campaign space
                    text_y = campaign_y + (campaign_spacing - PC.FONT_HEIGHT) // 2
                    display.drawText(campaign_name, 8, text_y, text_color)
                    display.drawText(tag_text, tag_x, text_y, text_color)
                else:
                    # Multi-line display
                    # Find a good split point
                    split_point = max_chars - 1
                    while split_point > 0 and campaign_name[split_point] != ' ':
                        split_point -= 1
                    
                    if split_point == 0:  # No space found, force split
                        first_line = campaign_name[:max_chars]
                        second_line = campaign_name[max_chars:]
                    else:
                        first_line = campaign_name[:split_point]
                        second_line = campaign_name[split_point+1:]
                    
                    # Calculate vertical centering for two lines
                    total_text_height = PC.FONT_HEIGHT * 2 + line_spacing
                    start_y = campaign_y + (campaign_spacing - total_text_height) // 2
                    
                    display.drawText(first_line, 8, start_y, text_color)
                    display.drawText(second_line, 8, start_y + line_spacing, text_color)
                    
                    # Show tag next to first line
                    display.drawText(tag_text, tag_x, start_y, text_color)
            
            # Draw cursor/selection indicator
            cursor_y = first_campaign_y + (selected - start_idx) * campaign_spacing + (campaign_spacing - PC.FONT_HEIGHT) // 2
            display.drawText(">", 0 + text_offset_x, cursor_y, PC.WHITE)
            
            # Draw back instruction with better positioning
            display.drawText("B:Back", 4 + text_offset_x, back_button_y, PC.LIGHTGRAY)
            
            display.update()
            
            if buttonU.justPressed():
                selected = (selected - 1) % len(campaigns)
                sleep(0.15)
            elif buttonD.justPressed():
                selected = (selected + 1) % len(campaigns)
                sleep(0.15)
            elif buttonA.justPressed():
                return campaigns[selected]
            elif buttonB.justPressed():
                return None
                
    def show_scrolling_text(self, title, text, continue_text="A to continue", type=0, actions=None):
        """Display scrolling text screen with title and content, optionally with action buttons"""
        width = PC.TEXTBOX_WIDTH
        height = PC.TEXTBOX_HEIGHT
        x_start, y_start, y_header = 0, 0, 0
        scrollbars_x = - 2
        if IS_THUMBY_COLOR:
            if type != 1: width = PC.WIDTH
            if type == 0:
                x_start = 4
                y_start = 15
                height = PC.HEIGHT -15
                scrollbars_x = - 6
                y_header = y_start
            if type == 1: y_start = 2
            if type == 2: 
                height -= 20
                y_start = 57
        display.setFont("/lib/font3x5.bin", 3, 5, 1)
        
        # Wrap text to fit screen width, respecting newlines
        wrapped_text = []
        paragraphs = text.split("\n")
        
        max_line_width = width - 4 - x_start
        
        for paragraph in paragraphs:
            if paragraph.strip() == "":
                wrapped_text.append("")
                continue
                
            words = paragraph.split()
            line = ""
            
            for word in words:
                test_line = line + word + " "
                test_width = len(test_line) * PC.FONT_WIDTH
                
                if test_width <= max_line_width:
                    line = test_line
                else:
                    wrapped_text.append(line)
                    line = word + " "
            
            if line:
                wrapped_text.append(line)
            
        # Calculate total text height and set up scrolling
        text_height = len(wrapped_text) * PC.FONT_HEIGHT
        scroll_pos = 0
        
        # Adjust available area based on whether we have actions
        if actions:
            available_area = height - 44  # Leave more space for action buttons
        else:
            available_area = height - 24
            
        max_scroll = max(0, text_height - available_area)
        
        last_scroll_time = ticks_ms()
        scroll_speed = 2
        
        # Action selection setup
        selected_action = 0 if actions else -1
        
        while True:
            display.fill(0)
            if self.background:
                self.background.run(type)
                
            # Draw header with title - center it
            title_x = (PC.WIDTH - len(title) * PC.FONT_WIDTH) // 2
            display.drawText(title, title_x, 4+y_header, PC.WHITE)
            display.drawLine(0, 18+y_header, PC.WIDTH, 18+y_header, PC.WHITE)
            
            # Draw text content with scrolling
            content_y = 24 - scroll_pos
            min_visible_y = 22
            max_visible_y = height - (32 if actions else 12)
            
            for line in wrapped_text:
                if min_visible_y < content_y < max_visible_y:
                    if line.strip():
                        display.drawText(line, 4+x_start, content_y+y_start, PC.LIGHTGRAY)
                content_y += PC.FONT_HEIGHT
            
            # Draw action buttons or continue prompt
            if actions:
                # Draw actions bar with solid background
                actions_y = PC.HEIGHT - PC.FONT_HEIGHT - 10
                display.drawFilledRectangle(0, actions_y, PC.WIDTH, 20, PC.BLACK)
                
                # Calculate action spacing
                total_actions = len(actions)
                if total_actions == 2:
                    positions = [4, PC.WIDTH - (len(actions[1]) * PC.FONT_WIDTH) - 4]
                elif total_actions == 3:
                    positions = [
                        4,
                        PC.WIDTH // 2 - (len(actions[1]) * PC.FONT_WIDTH // 2),
                        PC.WIDTH - (len(actions[2]) * PC.FONT_WIDTH) - 4
                    ]
                else:
                    # Fallback for other numbers of actions
                    spacing = PC.WIDTH // total_actions
                    positions = [i * spacing + 4 for i in range(total_actions)]
                
                # Draw each action
                for i, action in enumerate(actions):
                    color = PC.WHITE if i == selected_action else PC.LIGHTGRAY
                    display.drawText(action, positions[i], actions_y + 4, color)
            else:
                # Draw continue prompt at bottom (only if scrolled to end)
                if scroll_pos >= max_scroll:
                    continue_x = (PC.WIDTH - len(continue_text) * PC.FONT_WIDTH) // 2
                    display.drawText(continue_text, continue_x, PC.HEIGHT - PC.FONT_HEIGHT, PC.WHITE)
            
            # Draw scroll indicators
            if scroll_pos > 0:
                display.drawText("^", PC.WIDTH - PC.FONT_WIDTH + scrollbars_x, 22 + y_start, PC.WHITE)
            if scroll_pos < max_scroll:
                display.drawText("v", PC.WIDTH - PC.FONT_WIDTH + scrollbars_x, max_visible_y - 4 + y_start, PC.WHITE)
                
            display.update()
            
            # Handle input
            current_time = ticks_ms()
            
            # Immediate B button exit
            if buttonB.justPressed():
                return "back" if actions else None
            
            # Action selection (left/right navigation)
            if actions and buttonL.justPressed():
                selected_action = (selected_action - 1) % len(actions)
                sleep(0.15)
            elif actions and buttonR.justPressed():
                selected_action = (selected_action + 1) % len(actions)
                sleep(0.15)
            elif buttonA.justPressed():
                if actions:
                    # Return the selected action text (lowercase for consistency)
                    return actions[selected_action].lower()
                elif scroll_pos >= max_scroll:
                    # Only allow A to continue if scrolled to end (when no actions)
                    return None
            
            # Scrolling (only when no actions selected or when actions are present)
            elif buttonU.pressed() and scroll_pos > 0:
                if ticks_diff(current_time, last_scroll_time) > TEXT_SCROLL_DELAY:
                    scroll_pos -= scroll_speed
                    last_scroll_time = current_time
            elif buttonD.pressed() and scroll_pos < max_scroll:
                if ticks_diff(current_time, last_scroll_time) > TEXT_SCROLL_DELAY:
                    scroll_pos += scroll_speed
                    last_scroll_time = current_time


    def campaign_info_screen(self, campaign_title):
        """Show campaign info and ask to start new or continue using enhanced scrolling text"""
        campaign = self.campaigns[campaign_title]
        has_save = campaign_title in self.campaign_saves
        
        # Prepare actions based on whether save exists
        if has_save:
            actions = ["CONTINUE", "NEW", "BACK"]
        else:
            actions = ["START", "BACK"]
        
        # Use the enhanced show_scrolling_text method
        result = self.show_scrolling_text(
            title="Campaign Info",
            text=campaign_title+"\n\n"+campaign["description"],
            type=0,
            actions=actions
        )
        
        # Map results to expected return values
        if result == "continue" or result == "start":
            return "continue" if has_save and result == "continue" else "new"
        elif result == "new":
            return "new"
        else:  # "back" or any other result
            return "back"
      
    def show_mission_briefing(self, mission):
        """Show mission briefing for the current mission"""
        if not self.campaign_data or self.current_mission >= len(self.campaign_data["missions"]):
            return
            
        mission_data = self.campaign_data["missions"][self.current_mission]
        
        title = f"MISSION {self.current_mission + 1}"
        mission_name = mission_data['name']
        text = f"{mission_name}\n\n{mission_data['briefing']}"
        
        objectives = mission_data.get("objectives", {})
        if objectives:
            text += "\n\nMISSION OBJECTIVES:"
            if "survive_time" in objectives:
                text += f"\n- Survive for {objectives['survive_time']} seconds"
            if "kills" in objectives:
                text += f"\n- Destroy {objectives['kills']} enemies/asteroids"
        
        self.show_scrolling_text(title, text, type=1)

    def show_mission_debriefing(self, mission_score):
        """Show mission debriefing with score and continue story"""
        if not self.campaign_data or self.current_mission >= len(self.campaign_data["missions"]):
            return
            
        mission_data = self.campaign_data["missions"][self.current_mission]
        title = f"MISSION {self.current_mission + 1}"
        text = f"Mission Completed!\n\nScore: {mission_score}\nTotal: {self.total_score + mission_score}\n\n{mission_data['debriefing']}"
        
        self.show_scrolling_text(title, text, type=2)
        
        self.total_score += mission_score
        self.current_mission += 1
        self.save_progress()
        
        if self.current_mission >= len(self.campaign_data["missions"]):
            self.show_campaign_complete()
            return True
        
        return False

    def show_campaign_complete(self):
        """Show campaign completion screen"""
        if not self.campaign_data:
            return
            
        title = "CAMPAIGN COMPLETE"
        text = f"Total Score: {self.total_score}\n\n{self.campaign_data.get('outro', 'Congratulations on completing the campaign!')}"
        
        self.show_scrolling_text(title, text)
        
        if self.current_campaign in self.campaign_saves:
            del self.campaign_saves[self.current_campaign]
            self.save_progress()

    def show_message(self, title, message):
        """Show a simple message box"""
        display.fill(0)
        if self.background:
            self.background.run(0)
            
        # Draw box
        box_width = PC.WIDTH - 10
        box_height = 60
        box_x = 5
        box_y = 10
        
        display.drawRectangle(box_x, box_y, box_width, box_height, PC.WHITE)
        display.drawFilledRectangle(box_x, box_y, box_width, PC.FONT_HEIGHT + 4, PC.WHITE)
        
        # Draw title
        display.drawText(title, box_x + 4, box_y + 4, PC.BLACK)
        
        # Draw message (simple, no wrapping)
        display.drawText(message[:PC.WIDTH // PC.FONT_WIDTH], box_x + 4, box_y + PC.FONT_HEIGHT + 20, PC.WHITE)
        
        # Draw prompt
        prompt_text = "Press A to continue"
        display.drawText(prompt_text, box_x + 4, box_y + box_height - PC.FONT_HEIGHT - 10, PC.WHITE)
        
        display.update()
        
        while not buttonA.justPressed():
            display.update()
        
        sleep(0.2)

    @micropython.native
    def get_mission_config(self):
        """Get the configuration for the current mission"""
        if not self.campaign_data or self.current_mission >= len(self.campaign_data["missions"]):
            return None
            
        return self.campaign_data["missions"][self.current_mission]["config"]
        
    def get_mission_objectives(self):
        """Get the objectives for the current mission"""
        if not self.campaign_data or self.current_mission >= len(self.campaign_data["missions"]):
            return None
            
        return self.campaign_data["missions"][self.current_mission].get("objectives", {})

    def run_campaign_menu(self, background=None):
        """Main method to run the campaign selection and management"""
        self.background = background
        
        while True:
            campaign_title = self.select_campaign_menu()
            if not campaign_title:
                return None
                
            action = self.campaign_info_screen(campaign_title)
            if action == "back":
                continue
            elif not action:
                return None
                
            campaign_file = self.campaigns[campaign_title]["file"]
            if not self.load_campaign(campaign_file):
                self.show_message("Error", "Failed to load campaign")
                return None
                
            if action == "continue":
                self.load_progress(campaign_title)
            else:
                self.current_mission = 0
                self.total_score = 0
                if "intro" in self.campaign_data:
                    self.show_scrolling_text("INTRODUCTION", self.campaign_data["intro"])
            
            return self

    def run_post_mission_menu(self, mission_score):
        """Show post-mission menu with options to continue, save, or exit"""
        is_complete = self.show_mission_debriefing(mission_score)
        if is_complete:
            return "complete"
            
        selected = 0
        options = ["CONTINUE", "SAVE & EXIT"]
        
        while True:
            display.fill(0)
            if self.background:
                self.background.run(0)
                
            # Draw header
            header_text = "MISSION COMPLETE"
            title_x = (PC.WIDTH - len(header_text) * PC.FONT_WIDTH) // 2
            display.drawText(header_text, title_x, 4, PC.WHITE)
            display.drawLine(0, 18, PC.WIDTH, 18, PC.WHITE)
            
            # Draw options centered
            for i, option in enumerate(options):
                y_pos = 30 + i * (PC.FONT_HEIGHT + 10)
                x_pos = (PC.WIDTH - len(option) * PC.FONT_WIDTH) // 2
                display.drawText(option, x_pos, y_pos, PC.WHITE if i == selected else PC.LIGHTGRAY)
            
            display.update()
            
            if buttonU.justPressed():
                selected = (selected - 1) % len(options)
                sleep(0.15)
            elif buttonD.justPressed():
                selected = (selected + 1) % len(options)
                sleep(0.15)
            elif buttonA.justPressed():
                if selected == 0:
                    return "continue"
                else:
                    return "exit"

    def show_mission_failed(self, attempt, max_attempts):
        """Show mission failed screen with attempt information"""
        display.fill(0)
        if self.background:
            self.background.run(0)
            
        display.setFont("/lib/font5x7.bin", 5, 7, 1)
        text = "MISSION"
        x = (PC.WIDTH - len(text) * PC.FONT_WIDTH) // 2
        display.drawText(text, x, 20, PC.WHITE)
        text = "FAILED"
        x = (PC.WIDTH - len(text) * PC.FONT_WIDTH) // 2
        display.drawText(text, x, 40, PC.WHITE)
        display.update()
        sleep(1)
        
        display.setFont("/lib/font3x5.bin", 3, 5, 1)
        display.fill(0)
        if self.background:
            self.background.run(0)
            
        display.drawText(f"Attempt {attempt} of {max_attempts}", 4, 20, PC.WHITE)
        display.drawText("Press A to retry", 4, 40, PC.WHITE)
        display.update()
        
        while not buttonA.justPressed():
            display.update()
        sleep(0.2)

    def show_mission_success(self):
        """Show mission success screen"""
        display.fill(0)
        if self.background:
            self.background.run(0)
            
        display.setFont("/lib/font5x7.bin", 5, 7, 1)
        text = "MISSION"
        x = (PC.WIDTH - len(text) * PC.FONT_WIDTH) // 2
        display.drawText(text, x, 20, PC.WHITE)
        text = "COMPLETE"
        x = (PC.WIDTH - len(text) * PC.FONT_WIDTH) // 2
        display.drawText(text, x, 40, PC.WHITE)
        display.update()
        sleep(2)
        display.setFont("/lib/font3x5.bin", 3, 5, 1)