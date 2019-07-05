import numpy as np
import pandas as pd
import time
import os
import networkx as nx
from scipy.spatial.distance import pdist
from scipy.cluster.hierarchy import linkage,cut_tree

def corgenelength(mut,cangenes,esize,normbysample=True):
    """Function to normalize gene mutation scores by gene length.
    mut should be a dataframe of mutation scores with genes as columns and samples as rows. 
    (VERY IMPORTANT, IF OTHERWISE MATRIX SHOULD BE TRANSPOSED OR IT WON'T WORK!!!)
    
    cangenes should be a set of cancer associated genes.
    esize should be a dataframe of gene lengths.
    It also normalizes the gene mutation scores in a sample by the total mutations within the sample. (Can be deactivated with normbysample=False.)
    """
    #Subsets mutation data to cancer-associated genes.
    mut_cangenes = cangenes.intersection(set(mut.columns))
    mut = mut[list(mut_cangenes)]
    
    #Intersection of genes in the mutation data and the length data.
    mut_esize = list(mut_cangenes.intersection(set(esize.columns)))
    mut = mut[mut_esize]
    esize = esize[mut_esize]
    
    #Divide each number of mutations by gene size
    mut = mut.div(esize.iloc[0])
    
    #Drop samples (rows) without mutations (each column equals 0)
    mut = mut.drop(list(mut[(mut == 0).all(1)].index))
    
    #Normalize mutation score by patient number of mutations
    if(normbysample):
        mut["sum"]=mut.sum(axis=1) #Adds auxiliar column with the sum of columns (sum of mutation scores within a sample)
        mut = mut.div(mut["sum"],axis=0) #Corrects gene mutation scores in a sample by the total mutation score in the sample.
        mut = mut.drop(columns=["sum"])
    
    #Returns mut matrix of gene mutation scores by sample adjusted by length and total number of mutations within sample.
    #Sorted columns for niceness
    assert mut.shape!=(0,0),"Are you sure your mutation matrix has the proper orientation? Genes as columns, samples as rows."
    return mut[sorted(mut.columns)]

def convertgmt(gmtfile, cangenes):
    """This function takes as input the name of a gmt file containing lists of genes associated to pathways. 
    It outputs an adjacency matrix of genes and pathways. 
    It also subsets the genes to a list of cancer-associated genes. 
    """
    
    file = open(gmtfile) # Loads the gmt file
    pw = file.readlines() #Reads file into list of strings

    a = dict() #Sets up dictionary
    for entry in pw:
        u = entry[:-1].split("\t",-1) #Process each string separating genes and removing final \n.
        a[u[0]] = u[2:] #Sets dictionary key the pathway id, value the list of genes removing the link entry.

    #Set of all genes in the dictionary
    b=set()
    for i in a.keys():
        b = b.union(set(a[i]))

    C = sorted(list(b)) #List of genes in the file (sorted)
    P = sorted(a.keys()) #List of pathways in the file (sorted)
    
    G = nx.Graph(a) #Creates a bipartite graph from the dictionary
    A = nx.adjacency_matrix(G,nodelist=(C+P)).todense() #Creates the adjacency matrix of the graph G in the proper order. 
    #Note that this matrix is square with size len(C)+len(P), the biadjacency matrix caused issues with big files.
    
    #Builds a dataframe from the adjacency matrix and tags the rows and columns.
    sign_matrix = pd.DataFrame(A)
    sign_matrix.columns=C+P
    sign_matrix.index=C+P
    
    #Subsets the dataframe so it has as columns the genes and as rows the pathways. Orders for niceness.
    sign_matrix = sign_matrix[sorted(C)]
    sign_matrix = sign_matrix.loc[sorted(P)]
 
    #Subset pathways to cancer-associated genes
    sign_cangenes = cangenes.intersection(set(sign_matrix.columns))
    sign_matrix = sign_matrix[list(sign_cangenes)]
    
    return sign_matrix[sorted(sign_matrix.columns)]

def desparsify(mutdata,exonsize,gmtfile,cangenes,normMut=True):
    """Applies the sambar method to de-sparcify the mutation data using the pathway signatures in the gmtfile."""
    tinit = time.time()  
    
    #Gets corrected gene mutation scores. Subseted to cancer-associated genes.
    mutrate = corgenelength(mutdata,cangenes,exonsize,normMut)
    #Gets adjacency matrix of genes and pathways. Subseted to cancer-associated genes.
    sign_matrix = convertgmt(gmtfile,cangenes)

    #Match genes in both lists
    genes_ms = sorted(list(set(mutrate.columns).intersection(set(sign_matrix.columns))))
    ## Computes the number of genes in a pathway (before matching with mutation data).
    sm = sign_matrix.sum(1)
    
    #Matches genes in mutation data with genes in pathway data
    mutrate = mutrate[genes_ms]
    sign_matrix = sign_matrix[genes_ms]
    mt = mutrate
    #Corrects mutation rates by frequency in a pathway
    genefreq = list(sign_matrix.sum())
    mutrate = mutrate.div(genefreq).transpose()
    
    #This should be done here, otherwise the matching before checkpoint 2 might generate rows with only 0. SHOULD NOT BE COMMENTED
    sign_matrix = sign_matrix.drop(list(sign_matrix[(sign_matrix == 0).all(1)].index))
    sign_matrix = sign_matrix.transpose()
    sign_matrix = sign_matrix.drop(list(sign_matrix[(sign_matrix == 0).all(1)].index))
    sign_matrix = sign_matrix.transpose()
    
    #Matrix multiply dataframes to get the pathway mutation scores
    pathway_scores = sign_matrix.dot(mutrate).div(sm,axis=0)
    
    #Remove rows and columns with only 0.
    pathway_scores = pathway_scores.drop(list(pathway_scores[(pathway_scores == 0).all(1)].index))
    pathway_scores = pathway_scores.transpose()
    pathway_scores = pathway_scores.drop(list(pathway_scores[(pathway_scores == 0).all(1)].index))
    pathway_scores = pathway_scores.transpose()
    
    tfin = time.time()
    print("Runtime: ",tfin-tinit)
    
    return mt,pathway_scores

def binomial_dist(u,v):
    """Implementation of the binomial dissimilarity funcion or Millar distance from the vegan:vegdist package in R."""
    x,y=u,v
    nk = x+y
    lognk = np.nan_to_num(np.log(nk))
    t1 = np.nan_to_num((x*(np.log(x)-lognk)))
    t2 = np.nan_to_num((y*(np.log(y)-lognk)))
    dn = t1+t2+nk*np.log(2)
    d = sum(np.nan_to_num((dn/nk)))
    return np.where(d<0, 0, d)

def clustering(pt, kmin,kmax):
    """Computes the clustering for the pathways matrix and returns a dataframe with the groups with k clusters from kmin to kmax."""
    
    Y = pdist(pt.transpose(),binomial_dist) # Computes the distance matrix. pt is transposed because the pdist function takes rows as input and what we want to cluster are the samples.
    Z = linkage(Y,"complete") #Linkage of the clusters using the distance matrix and the complete method.
    
    #Building the output dataframe.
    df = pd.DataFrame()
    for k in range(kmin,kmax+1):
        R = cut_tree(Z,k) #Cuts the tree at k groups.
        u = [item for sublist in R for item in sublist]
        df["X"+str(k)] =u
        df.index = pt.columns
    return df.transpose()

def sambar(mut_file,esize_file,genes_file,gmtfile,normPatient=True,kmin=2,kmax=4):
    """Runs sambar and outputs the pt matrix, the mt matrix and the clustering matrix.
    mutfile -> matrix of mutations with genes as columns and samples as rows. Format CSV.
    esize_file -> file with genes and their length.
    genes_file -> file with list of cancer-associated genes.
    gmt_file -> genelist by pathway, format from MSigDB.
    normPatien -> Normalize mutation data by number of mutations in a sample.
    kmin,kmax -> Number of groups in the clustering.
    
    Outputs:
    mt_out.csv -> processed gene mutation scores.
    pt_out.csv -> pathway mutation scores
    clustergroups.csv -> matrix of pertinence to a group in the clustering.
    """
    mut = pd.read_csv(mut_file,index_col=0)
    esize = pd.read_csv(esize_file,index_col=0)
    file = open(genes_file) # Loads the gmt file
    gene_line = file.readline()
    genes = set(gene_line.split("\t"))
    
    os.mkdir("output")

    
    mt,pt = desparsify(mut,esize,gmtfile,genes,normPatient)
    
    pt.to_csv("output/pt_out.csv")
    mt.to_csv("output/mt_out.csv")
    
    groups = clustering(pt,kmin,kmax)
    groups.to_csv("output/clustergroups.csv")
    return pt,groups




