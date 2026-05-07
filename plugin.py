#!/usr/bin/env python3
###
# Licensed under the Supybot license
###
# Groq AI Plugin with Conversation Memory for Limnoria
# Works in both channels AND private messages
# Made with DeepSeek by aldcor

###

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.conf as conf
import supybot.registry as registry

import json
import requests
import re
from collections import deque, defaultdict

__author__ = "Your Name"
__version__ = "1.0.13"
__contributors__ = {}

# Configure plugin options
conf.registerPlugin('GroqWithMemory')
conf.registerChannelValue(conf.supybot.plugins.GroqWithMemory, 'apiKey',
    registry.String('', """Groq API key"""))
conf.registerChannelValue(conf.supybot.plugins.GroqWithMemory, 'model',
    registry.String('llama-3.1-8b-instant', """Model to use for Groq API"""))
conf.registerChannelValue(conf.supybot.plugins.GroqWithMemory, 'memorySize',
    registry.PositiveInteger(10, """Number of exchanges to remember per user"""))
conf.registerChannelValue(conf.supybot.plugins.GroqWithMemory, 'maxTokens',
    registry.PositiveInteger(800, """Maximum tokens in response. Lower = shorter responses."""))

class GroqWithMemory(callbacks.Plugin):
    """Groq AI chatbot with conversation memory for IRC."""
    
    def __init__(self, irc):
        self.__parent = super(GroqWithMemory, self)
        self.__parent.__init__(irc)
        memory_size = self.registryValue('memorySize')
        self.conversations = defaultdict(lambda: deque(maxlen=memory_size * 2))
    
    def _clean_response(self, text):
        """Remove escaped newlines and backslashes completely."""
        if not text:
            return text
        
        # Convert literal \n to actual newlines
        text = text.replace('\\n', '\n')
        text = text.replace('\\\\n', '\n')
        
        # Remove ALL remaining backslashes
        text = text.replace('\\', '')
        
        # Clean up multiple newlines and spaces
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        text = re.sub(r' \n', '\n', text)
        text = re.sub(r'\n ', '\n', text)
        
        return text.strip()
    
    def _trim_conversation(self, messages, max_tokens=3000):
        """Trims the conversation history to stay within token limits."""
        if not messages:
            return messages
        
        system_message = None
        conversation_messages = []
        
        for msg in messages:
            if msg.get('role') == 'system':
                system_message = msg
            else:
                conversation_messages.append(msg)
        
        trimmed_messages = []
        total_tokens = 0
        
        if system_message:
            trimmed_messages.append(system_message)
        
        temp_messages = []
        for msg in reversed(conversation_messages):
            msg_tokens = len(msg['content']) // 4 + 1
            if total_tokens + msg_tokens <= max_tokens:
                temp_messages.insert(0, msg)
                total_tokens += msg_tokens
            else:
                break
        
        trimmed_messages.extend(temp_messages)
        return trimmed_messages
    
    @wrap(['text'])
    def ask(self, irc, msg, args, question):
        """Ask Groq a question. Works in channels AND private messages.
        
        Example: @ask What is the capital of France?
        """
        if not question or question.strip() == '':
            irc.reply("Usage: @ask <your question>")
            return
        
        user_identifier = msg.prefix
        
        # FIX: Determine where to send the response (works in both channels and PMs)
        if msg.args[0] == irc.nick:
            # Private message - reply to the sender's nickname
            target = msg.nick
        else:
            # Channel message - reply to the channel
            target = msg.args[0]
        
        # Send processing indicator
        #irc.queueMsg(ircmsgs.privmsg(target, "Processing..."))
        
        try:
            api_key = self.registryValue('apiKey')
            if not api_key:
                irc.queueMsg(ircmsgs.privmsg(target, "Error: API key not set. Use: @config supybot.plugins.GroqWithMemory.apiKey YOUR_KEY"))
                return
            
            model = self.registryValue('model')
            max_tokens = self.registryValue('maxTokens')
            
            # Get conversation history
            history = self.conversations[user_identifier]
            messages = list(history) if history else []
            
            # Add user question
            messages.append({"role": "user", "content": question})
            
            # Add system prompt
            system_prompt = {
                "role": "system",
                "content": "You are a helpful assistant. Be concise. Use real line breaks. Never write backslash-n."
            }
            if not messages or messages[0].get('role') != 'system':
                messages.insert(0, system_prompt)
            
            # Trim conversation
            messages = self._trim_conversation(messages, max_tokens=3000)
            
            # Make API call to Groq
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": max_tokens
                },
                timeout=60
            )
            
            # Handle HTTP errors
            if response.status_code != 200:
                irc.queueMsg(ircmsgs.privmsg(target, f"Error: HTTP {response.status_code}"))
                return
            
            # Parse and clean response
            data = response.json()
            raw_response = data['choices'][0]['message']['content'].strip()
            cleaned_response = self._clean_response(raw_response)
            
            # Store in conversation history
            self.conversations[user_identifier].append({"role": "user", "content": question})
            self.conversations[user_identifier].append({"role": "assistant", "content": cleaned_response})
            
            # Send response line by line (prevents IRC formatting issues)
            for line in cleaned_response.split('\n'):
                if line.strip():
                    irc.queueMsg(ircmsgs.privmsg(target, line))
            
        except requests.exceptions.Timeout:
            irc.queueMsg(ircmsgs.privmsg(target, "Error: Request timed out. Please try again."))
        except requests.exceptions.ConnectionError:
            irc.queueMsg(ircmsgs.privmsg(target, "Error: Cannot reach Groq API. Check your network."))
        except Exception as e:
            irc.queueMsg(ircmsgs.privmsg(target, f"Error: {str(e)[:200]}"))
    
    @wrap([])
    def forget(self, irc, msg, args):
        """Forget your conversation history.
        
        Example: @forget
        """
        user = msg.prefix
        
        # Determine where to send the response
        if msg.args[0] == irc.nick:
            target = msg.nick
        else:
            target = msg.args[0]
        
        if user in self.conversations:
            del self.conversations[user]
            irc.queueMsg(ircmsgs.privmsg(target, "Conversation history forgotten. Starting fresh!"))
        else:
            irc.queueMsg(ircmsgs.privmsg(target, "No conversation history to forget."))
    
    @wrap([])
    def memorysize(self, irc, msg, args):
        """Show current memory size.
        
        Example: @memorysize
        """
        current_size = self.registryValue('memorySize')
        
        # Determine where to send the response
        if msg.args[0] == irc.nick:
            target = msg.nick
        else:
            target = msg.args[0]
        
        irc.queueMsg(ircmsgs.privmsg(target, f"I remember the last {current_size} exchanges per user."))
    
    @wrap(['int'])
    def setmemory(self, irc, msg, args, new_size):
        """Change memory size (bot owner only).
        
        Example: @setmemory 7
        """
        if not ircutils.isOwner(msg):
            irc.error("Only the bot owner can change memory size.", Raise=True)
            return
        
        if new_size < 1 or new_size > 20:
            irc.reply("Memory size must be between 1 and 20.")
            return
        
        conf.supybot.plugins.GroqWithMemory.memorySize.setValue(new_size)
        
        # Update existing conversations
        for user_id in list(self.conversations.keys()):
            old_items = list(self.conversations[user_id])
            self.conversations[user_id] = deque(old_items, maxlen=new_size * 2)
        
        irc.reply(f"Memory size changed to {new_size} exchanges.")
    
    @wrap(['int'])
    def setmaxtokens(self, irc, msg, args, max_tokens):
        """Set max tokens (50-4000). Lower = shorter responses.
        
        Example: @setmaxtokens 500
        """
        if not ircutils.isOwner(msg):
            irc.error("Only the bot owner can change max tokens.", Raise=True)
            return
        
        if max_tokens < 50 or max_tokens > 4000:
            irc.reply("Max tokens must be between 50 and 4000.")
            return
        
        conf.supybot.plugins.GroqWithMemory.maxTokens.setValue(max_tokens)
        irc.reply(f"Max tokens set to {max_tokens}. {'Short responses' if max_tokens < 500 else 'Normal responses'}")
    
    @wrap([])
    def showmaxtokens(self, irc, msg, args):
        """Show current max tokens setting.
        
        Example: @showmaxtokens
        """
        current = self.registryValue('maxTokens')
        
        # Determine where to send the response
        if msg.args[0] == irc.nick:
            target = msg.nick
        else:
            target = msg.args[0]
        
        irc.queueMsg(ircmsgs.privmsg(target, f"Current max tokens: {current}"))
    
    def die(self):
        """Clean up when plugin is unloaded."""
        self.conversations.clear()
        if hasattr(self, '_GroqWithMemory__parent'):
            self.__parent.die()

Class = GroqWithMemory
