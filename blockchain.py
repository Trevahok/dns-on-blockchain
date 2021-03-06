import random
import hashlib, json 
import requests
from urllib.parse import urlparse
from textwrap import dedent
from uuid import uuid4
from flask import Flask , jsonify , request, render_template, redirect
from time import time
from flask_cors import CORS

port = 0

class Blockchain():
    
    def __init__(self):
        self.chain = []
        self.current_transactions= []
        self.nodes = set()
        #genesis block
        self.new_block(previous_hash=1, proof=100)

    def new_block(self, proof , previous_hash=None):
        block ={
            'index': len(self.chain) + 1 ,
            'timestamp' : time(), 
            'transactions': self.current_transactions,
            'proof' : proof, 
            'previous_hash': previous_hash or self.hash(self.chain[-1])
        }
        self.current_transactions=[]
        self.chain.append(block)
        return block

    def new_transaction(self,url , ip):
        self.current_transactions.append(
            {
                'url': url,
                'ip' : ip
            }
        )
        return self.last_block['index']+1

    @staticmethod
    def hash(block):
        block_string = json.dumps(block , sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        return self.chain[-1] 
    def proof_of_work(self , last_proof):
        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof+=1
        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:5]== '00000'

    def register_node(self , address, flag):
        parsed_url = urlparse(address)
        if parsed_url.netloc != "":
            if flag == 1:
                self.trigger_flood_nodes(address)
                for node in self.nodes:
                    node = "http://" + node
                    requests.post(url=f'http://{parsed_url.netloc}/nodes/register', json={
                        'nodes': [node],
                        'flag': 0
                    })
            self.nodes.add(parsed_url.netloc)

    def valid_chain(self , chain):
        last_block = chain[0]
        for current_index in range(1 , len(chain)):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print('\n----------\n')
            if block['previous_hash']!=self.hash(last_block):
                return False
            if not self.valid_proof(last_block['proof'] , block['proof']):
                return False
            last_block = block
        else:
            return True

    def resolve_conflicts(self):
        neighbours = self.nodes
        new_chain = None
        max_length = len(self.chain)
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')
            if response.status_code ==200:
                length = response.json()['length']
                chain = response.json()['chain']
                if length >= max_length and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain
        if new_chain:
            self.chain = new_chain
            return True
        return False

    def triggered_flood_chain(self):
        for node in self.nodes:
            requests.get(f'http://{node}/nodes/resolve')

    def trigger_flood_nodes(self,address):
        for node in self.nodes:
            requests.post(url=f'http://{node}/nodes/register', json={
                'nodes': [address] ,
                'flag': 0
            })
 
    def redundancy(self,url):
        for block in self.chain:
            for i in block['transactions']:
                if i['url'] == str(url):
                    return True
        else:
            return False


# Flask API code here

app = Flask(__name__)
node_identifier = str(uuid4()).replace('-', '')

CORS(app)
blockchain = Blockchain()

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/mine', methods= ['GET'])
def mine():
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    with open("data/"+str(port)+"_chain.json", "w") as file:
        json.dump(blockchain.chain, file)

    response = {
        'message' : "New Block Forged",
        'index': block['index'] , 
        'transactions': block['transactions'],
        'proof': block['proof'],
        'previous_hash': block['previous_hash'],
    }
    blockchain.triggered_flood_chain()
    return jsonify(response) , 200


@app.route('/transactions', methods=['GET'])
def full_transactions():
    return jsonify({
        'transactions': blockchain.current_transactions
    })

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()
    required = ['url', 'ip']
   
    if not all(k in values for k in required):
        return 'missing values' , 400
  
    if blockchain.redundancy(values['url']):
        return jsonify({'message': 'url already taken.'})
    if urlparse(values['url']).netloc != "":
        index = blockchain.new_transaction(urlparse(values['url']).netloc , values['ip'])
        response = {'message' : f'Transaction will be added to Block {index} '}
        return jsonify(response) , 201
    else:
        return jsonify({"message": "Invalid url!"}), 201

@app.route('/chain' , methods=['GET'])
def full_chain():
    response={
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200

@app.route('/nodes', methods=['GET'])
def full_nodes():
    return jsonify({
        'nodes': list(blockchain.nodes)
    })

@app.route('/nodes/register', methods= ['POST'])
def register_nodes():
    values = request.get_json()
    nodes = values.get('nodes')
    flag = values.get('flag')
    print(flag)
    if nodes is None:
        return 'Error: Please supply a valid list of nodes' , 400
    for node in nodes:
        blockchain.register_node(node, flag)
    response = {
        'message' : 'new nodes have been added', 
        'total_nodes': list(blockchain.nodes)
    }
    blockchain.resolve_conflicts()

    with open("data/"+str(port)+"_chain.json", "w") as file:
        json.dump(blockchain.chain, file)

    return jsonify(response) , 201


@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        with open("data/"+str(port)+"_chain.json", "w") as file:
            json.dump(blockchain.chain, file)
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain,
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain,
        }
    return jsonify(response), 200

@app.route('/url/<url>', methods=['GET'])
def red(url):
    print(url)
    for block in reversed(blockchain.chain):
        for i in block['transactions']:
                if i['url'] == str(url):
                    return jsonify({"Flag": True, "IP": i['ip']})
    return jsonify({"Flag": False, "Message": "Error 404! Not found"})
                    
if __name__ == "__main__":
    port = int(input('Enter port: '))
    try:
        with open("data/"+str(port)+"_chain.json", "r") as file:
            blockchain.chain = json.loads(file.read())
    except:
        file = open("data/"+str(port)+"_chain.json", "w")
        file.close()
    app.run(host='0.0.0.0', port=port, debug=True)