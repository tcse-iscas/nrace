var graphviz = require('graphviz'),
    path = require('path'),
    fs = require('fs'),
    mkdirp = require('mkdirp'),
    logger = require('../../../../driver/logger.js').logger,
    EdgeName2Type = require('../../HappensBeforeGraph').EdgeName2Type;

/** Configuration for graphViz */
var common = require('../../../../test/common');
var graphVizDir = common.TOOL_HOME + path.sep + 'test/output-graphviz';

/** this variable is used to debug. true is to debug*/
var debug = false;
var debugHelper = require('../../debug').debugHelper,
    print_array = require('../../debug').print_array,
    writeObj = require('../../debug').writeObj;

var exports = module.exports = {};

exports.drawGraph = function (hbGraph, outputFileName, warningNodes) {
    logger.info('start to draw vGraph ...');
    console.log('graphVizDir: ', graphVizDir);

    //console.log('****', EdgeName2Type);
    if (debug) {
        console.log('hello world');
        debugHelper(hbGraph.fileIONodes);
        Object.keys(hbGraph.fileIONodes).forEach(function (lineno) {
            hbGraph.fileIONodes
            var rcd = hbGraph.fileIONodes[lineno];
            if (rcd.isAsync) {
                debugHelper('fileRcd:' + lineno);
                //writeObj(rcd);
            }
        });
    }

    /** Create the digraph */
    var vGraph = graphviz.digraph('HappensBeforeGraph'),
        //allNodes = {};
        eventNodes = {},
        fileIONodes = {},
        virtualEventNodes = {};
    
    /** Create nodes for digraph */
    /** Process eventNodes */
    for (var i = 0; i < hbGraph.eventNodes.length; i++) {
        /** Note, eventNodes is a sparse array */
        var event = hbGraph.eventNodes[i];
        if (event != undefined) {
            var node = vGraph.addNode(event.id, {
                'color': common.COLOR.GREY,
                'style': common.STYLE.FILLED,
                //'shape': common.SHAPE.CIRCLE,
                //'fontname': 'helvetica',
            });
            eventNodes[node.id] = node;
        }
    }

    /** Process IONodes */
    
    Object.keys(hbGraph.fileIONodes).forEach(function (lineno) {
        var rcd = hbGraph.fileIONodes[lineno];
        if (rcd.isAsync) {
            var node = vGraph.addNode('IO' + rcd.lineno, {
                'color': common.COLOR.GREEN,
                'style': common.STYLE.FILLED,
                //'shape': common.SHAPE.CIRCLE,
                //'fontname': 'helvetica',
            });
            fileIONodes[node.id] = node;
        }
    });

    /** Process virtual event nodes */
    
    for (var [id, virtualEvent] of hbGraph.virtualEvents.entries()) {
        var node = vGraph.addNode(id, {
            'color': common.COLOR.PURPLE,
            'style': common.STYLE.FILLED,
            //'shape': common.SHAPE.CIRCLE,
            //'fontname': 'helvetica',
        })
        virtualEventNodes[id] = node;
    }
    /*
    console.log('virtualEventNodes:')
    Object.keys(virtualEventNodes).forEach(function (id) {
        var node = virtualEventNodes[id]
        debugHelper('#' + node.id);
        writeObj(node);
    });*/

    /** Create edges for digraph */
    
    for (var i = 0; i < hbGraph.eventNodes.length; i++) {
        var event = hbGraph.eventNodes[i];
        //Note, eventNodes is a sparse array 
        if (event != undefined) {
            if (!event.hasOwnProperty('edges')) continue;
            var firstNode = eventNodes[event.id];
            var edges = event.edges;
            Object.keys(edges).forEach(function (edgeType) {
                //TODO: map type name to type name id
                /** Register2Trigger */
                if (edgeType == 0) {
                    edges[edgeType].forEach(function (nextEventId) {
                        if (virtualEventNodes[nextEventId] == undefined) {
                            logger.error('Register2Trigger: ' + nextEventId + ' not exist');
                            return;
                        }
                        var vEdge = vGraph.addEdge(firstNode, virtualEventNodes[nextEventId]);
                        vEdge.set( "color", "red" );
                    });
                } else if (edgeType == 1) {
                    /** Register2IO */
                    edges[edgeType].forEach(function (nextIOId) {
                        if (fileIONodes['IO' + nextIOId] == undefined) {
                            logger.error('Register2IO: IO' + nextIOId + ' not exist');
                            return;
                        }
                        var vEdge = vGraph.addEdge(firstNode, fileIONodes['IO' + nextIOId]);
                        vEdge.set('color', 'green');
                    });
                } else if (edgeType == 4) {
                    /** FIFO */
                    edges[edgeType].forEach(function (nextEventId) {
                        if (eventNodes[nextEventId] == undefined) {
                            logger.error('FIFO: event #' + nextEventId + ' not exist');
                            return;
                        }
                        var vEdge = vGraph.addEdge(firstNode, eventNodes[nextEventId]);
                        vEdge.set('color', 'grey');
                    });
                }
            });
        }
    }

    /** Create Trigger2Follower edge */
    
    for (var [id, virtualEvent] of hbGraph.virtualEvents.entries()) {
        var edges = virtualEvent.edges;
        if (!edges.hasOwnProperty('2')) {
            logger.error('This triggering event has no follower event');
            return;
        }
        var followerId = edges[2][0],
            follower = eventNodes[followerId],
            vEdge = vGraph.addEdge(virtualEventNodes[id], follower);
            vEdge.set('color', 'yellow');
    }

    /** Create IO2Follower edge*/

    /*console.log('Start to create IO2Follower edge');
    Object.keys(eventNodes).forEach(function (id) {
        console.log('id: ', id);
    });*/
    
    Object.keys(hbGraph.fileIONodes).forEach(function (lineno) {
        var rcd = hbGraph.fileIONodes[lineno];
        if (rcd.isAsync && rcd.hasOwnProperty('edges')) {
            var edges = rcd.edges;
            if (!edges.hasOwnProperty('3')) {
                logger.error('This async file IO has no followerCb');
                return;
            }
            var triggerIO = fileIONodes['IO' + lineno],
                followCbId = edges[3][0],
                followCb = eventNodes[followCbId],
                vEdge = vGraph.addEdge(triggerIO, followCb);
            vEdge.set("color", 'blue');
        }
    });

    /** Create warning nodes as additional nodes for digraph */

    /** Path of output file */
    
    mkdirp.sync(graphVizDir);
    console.log( vGraph.to_dot() );
    vGraph.setGraphVizPath( "/usr/local/bin" );
    vGraph.output('png', 'test02.png');
    //vGraph.output('png', path.join(graphVizDir, path.sep, outputFileName) + '.png');
};