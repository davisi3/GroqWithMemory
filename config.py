import supybot.conf as conf
import supybot.registry as registry

def configure(advanced):
    conf.registerPlugin('GroqWithMemory', True)

GroqWithMemory = conf.registerPlugin('GroqWithMemory')

conf.registerGlobalValue(GroqWithMemory, 'apiKey',
    registry.String('', """Groq API key from console.groq.com""", private=True))

conf.registerGlobalValue(GroqWithMemory, 'memorySize',
    registry.PositiveInteger(5, """Number of previous exchanges to remember per user"""))

conf.registerGlobalValue(GroqWithMemory, 'model',
    registry.String('mixtral-8x7b-32768', """Groq model to use (mixtral-8x7b-32768, llama3-70b-8192, llama3-8b-8192, gemma2-9b-it)"""))

conf.registerGlobalValue(GroqWithMemory, 'maxTokens',
    registry.PositiveInteger(1024, """Maximum tokens in response"""))
