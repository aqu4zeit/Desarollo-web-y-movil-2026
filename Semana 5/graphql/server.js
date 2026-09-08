const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');

const {ApolloServer, gql} = require('apollo-server-express');
const Cliente = require('./models/clientes');

mongoose.connect('mongodb://localhost:27017/UNAB');
const typeDefs = gql`
    type Cliente{
        id: ID!
        nombre: String!
        pass: String!
    }

    input ClienteInput{
        nombre: String!
        pass: String!
    }
    type Alert{
        message: String
    }
    type Query{
        getClientes: [Cliente]
        getClientesByID(id: ID!): Cliente
    }
    type Mutation{
       addCliente(input: ClienteInput): Cliente
       updCliente(id: ID!, input: ClienteInput): Cliente
       delCliente(id: ID!): Alert
    }
`;

const resolvers ={
    Query: {
        async getClientes(obj){
            const clientes = await Cliente.find();
            return clientes;
        },
        async getClientesByID(obj, {id}){
            const clienteBus = await Cliente.findById(id);
            if (clienteBus == null){
                return null;
            }else {
                return clienteBus;
            }
        }
    },
    Mutation: {
        async addCliente(obj, {input}){
            const cliente = new Cliente(input);
            await cliente.save();
            return cliente;
        },
        async updCliente(obj, {id, input}){
            const cliente = await Cliente.findByIdAndUpdate(id, input);
            return cliente;
        },
        async delCliente(obj, {id}){
            await Cliente.deleteOne({_id: id});
            return {
                message: "Cliente Eliminado"
            }
        }
    }
};

let apolloServer = null;
const corsOption = {
    origin: "http://localhost:8090",
    Credential: false
};

async function startServer(){
    apolloServer = new ApolloServer({typeDefs, resolvers, corsOption});
    await apolloServer.start();
    apolloServer.applyMiddleware({app, cors: false});
}

startServer();
const app = express();
app.use(cors());
app.listen(8090, function(){
    console.log("Graphql iniciado");
});