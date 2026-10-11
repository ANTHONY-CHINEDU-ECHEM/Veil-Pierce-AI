# Builds a small demonstration snapshot and starts the service.
# Used as the container start command. Change the company count as needed.
veilpierce build synth.n_companies=50000 && veilpierce serve host=0.0.0.0 port=8000
